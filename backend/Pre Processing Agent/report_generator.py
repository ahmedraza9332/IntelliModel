import argparse
import json
from pathlib import Path

import pandas as pd
import numpy as np
from pandas.api import types as pdt

def generate_compact_report(df: pd.DataFrame, target: str):
    report = {}

    # ============================
    # 1. Dataset overview (short)
    # ============================
    n_rows, n_cols = df.shape
    report["dataset_overview"] = {
        "rows": n_rows,
        "columns": n_cols,
        "target_column": target,
        "target_type": str(df[target].dtype),
        "dataset_size_flag": "small" if n_rows < 1000 else "medium" if n_rows < 10000 else "large"
    }

    # ============================
    # 2. Target column analysis
    # ============================
    tgt = df[target]

    if tgt.dtype == "object" or tgt.dtype.name == "category":
        value_counts = tgt.value_counts(normalize=True).round(3).to_dict()
        imbalance = max(value_counts.values()) if len(value_counts) > 1 else 1.0

        report["target_analysis"] = {
            "type": "categorical",
            "unique_classes": int(tgt.nunique()),
            "top_classes": dict(list(value_counts.items())[:5]),
            "class_imbalance_ratio": imbalance,
            "missing_percent": float(tgt.isna().mean().round(3)),
        }
        # Flag for LLM
        flags = []
        if imbalance > 0.7:
            flags.append("target_imbalanced")
    else:
        skew = float(tgt.skew().round(3))
        report["target_analysis"] = {
            "type": "numeric",
            "min": float(tgt.min()),
            "max": float(tgt.max()),
            "mean": float(tgt.mean()),
            "std": float(tgt.std()),
            "missing_percent": float(tgt.isna().mean().round(3)),
            "skew": skew,
        }
        # Flags
        flags = []
        if abs(skew) > 1:
            flags.append("target_skewed")

    # ============================
    # 3. Column-level summary
    # ============================
    col_summary = {}
    numeric_skewed = []
    numeric_outliers = []
    cat_features = []

    for col in df.columns:
        if col == target:
            continue
        
        c = df[col]
        info = {"dtype": str(c.dtype), "missing_percent": float(c.isna().mean().round(3))}

        # Boolean – treat like categorical to avoid numeric ops on booleans
        if pdt.is_bool_dtype(c):
            top_vals = c.value_counts(normalize=True).round(3).head(3).to_dict()
            info.update({
                "unique_values": int(c.nunique()),
                "top_categories": top_vals
            })
            cat_features.append(col)

        # Numeric
        elif pdt.is_numeric_dtype(c):
            mean_val = float(c.mean()) if c.count() else None
            std_val = float(c.std()) if c.count() else None
            skew_val = float(c.skew().round(3)) if c.count() else None
            outlier_frac = float(
                ((c < (c.quantile(0.25) - 1.5 * (c.quantile(0.75)-c.quantile(0.25)))) |
                 (c > (c.quantile(0.75) + 1.5 * (c.quantile(0.75)-c.quantile(0.25))))).mean().round(3)
            )
            info.update({
                "mean": mean_val,
                "std": std_val,
                "skew": skew_val,
                "outlier_fraction": outlier_frac
            })
            if abs(skew_val) > 1:
                numeric_skewed.append(col)
            if outlier_frac > 0.05:
                numeric_outliers.append(col)

        # Categorical
        elif c.dtype == "object" or c.dtype.name == "category":
            top_vals = c.value_counts(normalize=True).round(3).head(3).to_dict()
            info.update({
                "unique_values": int(c.nunique()),
                "top_categories": top_vals
            })
            cat_features.append(col)

        # Datetime
        elif pdt.is_datetime64_any_dtype(c):
            info.update({
                "min_date": str(c.min()) if c.count() else None,
                "max_date": str(c.max()) if c.count() else None
            })

        col_summary[col] = info

    report["columns"] = col_summary

    # ============================
    # 4. Correlation with target
    # ============================
    corr_report = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col == target:
            continue
        try:
            corr_report[col] = float(df[[col, target]].corr().iloc[0,1])
        except:
            pass

    if len(corr_report) > 0:
        corr_report = dict(sorted(corr_report.items(), key=lambda x: abs(x[1]), reverse=True)[:5])

    report["top_correlated_with_target"] = corr_report

    # ============================
    # 5. High-level flags for LLM
    # ============================
    issues = []

    # Missing values >30%
    high_missing = df.columns[df.isna().mean() > 0.3].tolist()
    if high_missing:
        issues.append(f"Columns with very high missing values: {high_missing}")
        flags.append("high_missing_columns")

    # High cardinality
    high_card = [col for col in cat_features if df[col].nunique() > 30]
    if high_card:
        issues.append(f"High-cardinality categorical columns: {high_card}")
        flags.append("high_cardinality_categorical")

    # Skewed numeric features
    if numeric_skewed:
        issues.append(f"Highly skewed numeric columns: {numeric_skewed}")
        flags.append("numeric_skewed_features")

    # Outlier-heavy numeric features
    if numeric_outliers:
        issues.append(f"Numeric columns with high outlier fraction: {numeric_outliers}")
        flags.append("numeric_outlier_features")

    # Many categorical features
    if len(cat_features) / max(1, n_cols-1) > 0.5:
        flags.append("many_categorical_features")

    report["high_level_flags"] = issues
    report["llm_flags"] = flags

    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a compact EDA report for a CSV dataset.")
    parser.add_argument("--csv", required=True, type=Path, help="Path to the CSV file to analyze.")
    parser.add_argument("--target", required=True, help="Name of the target column in the dataset.")
    parser.add_argument("--output", type=Path, help="Optional path to save the generated report as JSON.")
    return parser.parse_args()


def main():
    args = _parse_args()
    df = pd.read_csv(args.csv)
    if args.target not in df.columns:
        raise ValueError(f"Target column '{args.target}' not found in {args.csv}")

    report = generate_compact_report(df, args.target)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(f"Report saved to {args.output}")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
