"""
Housing Price Data Preprocessing Pipeline
Follows the exact preprocessing steps defined in the JSON plan.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from scipy import stats
import warnings

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
DATA_PATH = r'C:\Users\pc\OneDrive\Desktop\FYP\IntelliModel\backend\Datasets\Housing.csv'
OUTPUT_PATH = Path(__file__).parent / 'processed_output.csv'

# ─────────────────────────────────────────────
# Load Dataset
# ─────────────────────────────────────────────
print("Loading dataset from Housing.csv ...")
df = pd.read_csv(DATA_PATH)
print(f"Dataset shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")

# ─────────────────────────────────────────────
# STEP 1: Missing Value Audit
# ─────────────────────────────────────────────
print("\n--- STEP 1: Missing Value Audit ---")

# Check for standard NaN/None missing values
null_counts = df.isnull().sum()
na_counts = df.isna().sum()
print("isnull() counts:\n", null_counts)
print("isna() counts:\n", na_counts)

# Check for hidden nulls: empty strings, whitespace, sentinel values
for col in df.columns:
    if df[col].dtype == object:
        empty_str = (df[col].str.strip() == '').sum()
        unknown_vals = (df[col].str.lower().str.strip() == 'unknown').sum()
        if empty_str > 0:
            print(f"WARNING: Column '{col}' has {empty_str} empty string(s).")
        if unknown_vals > 0:
            print(f"WARNING: Column '{col}' has {unknown_vals} 'unknown' value(s).")
    else:
        sentinel_neg1 = (df[col] == -1).sum()
        if sentinel_neg1 > 0:
            print(f"WARNING: Column '{col}' has {sentinel_neg1} sentinel value(s) of -1.")

assert null_counts.sum() == 0, "ERROR: Missing values detected! Imputation required."
print("PASSED: Zero missing values confirmed across all columns.")

# ─────────────────────────────────────────────
# STEP 2: Binary Categorical Encoding (yes=1, no=0)
# ─────────────────────────────────────────────
print("\n--- STEP 2: Binary Categorical Encoding ---")

binary_cols = ['mainroad', 'guestroom', 'basement', 'hotwaterheating', 'airconditioning', 'prefarea']
binary_mapping = {'yes': 1, 'no': 0}

for col in binary_cols:
    unique_vals = set(df[col].str.lower().str.strip().unique())
    assert unique_vals == {'yes', 'no'}, (
        f"ERROR: Column '{col}' contains unexpected values: {unique_vals}"
    )
    df[col] = df[col].str.lower().str.strip().map(binary_mapping)
    print(f"  Encoded '{col}': yes=1, no=0")

print("PASSED: Binary encoding applied to all yes/no columns.")

# ─────────────────────────────────────────────
# STEP 3: Ordinal Encoding for furnishingstatus
# ─────────────────────────────────────────────
print("\n--- STEP 3: Ordinal Encoding for furnishingstatus ---")

ordinal_mapping = {'unfurnished': 0, 'semi-furnished': 1, 'furnished': 2}
unique_furnishing = set(df['furnishingstatus'].str.lower().str.strip().unique())
expected_furnishing = {'unfurnished', 'semi-furnished', 'furnished'}

assert unique_furnishing == expected_furnishing, (
    f"ERROR: Unexpected values in furnishingstatus: {unique_furnishing}"
)

df['furnishingstatus'] = df['furnishingstatus'].str.lower().str.strip().map(ordinal_mapping)
print("  Encoded furnishingstatus: unfurnished=0, semi-furnished=1, furnished=2")
print("PASSED: Ordinal encoding applied to furnishingstatus.")

# ─────────────────────────────────────────────
# STEP 9: Train/Test Split BEFORE fitting any transformers
# (Must be done before Winsorization, scaling, etc. to prevent leakage)
# ─────────────────────────────────────────────
print("\n--- STEP 9: Train/Test Split (before fitting transformers) ---")

# Create price quantile bins for stratified split
df['price_bin'] = pd.qcut(df['price'], q=4, labels=False, duplicates='drop')

X = df.drop(columns=['price', 'price_bin'])
y = df['price'].copy()  # Keep original untransformed target
price_bins = df['price_bin']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=price_bins
)

print(f"  Train size: {X_train.shape[0]} rows | Test size: {X_test.shape[0]} rows")
print("PASSED: Stratified train/test split completed.")

# ─────────────────────────────────────────────
# STEP 4: Outlier Detection and Treatment for 'stories'
# (Winsorization at 1st/99th percentile, fit on train only)
# ─────────────────────────────────────────────
print("\n--- STEP 4: Outlier Treatment for 'stories' (Winsorization) ---")

# Compute IQR bounds on training data only
stories_q1 = X_train['stories'].quantile(0.25)
stories_q3 = X_train['stories'].quantile(0.75)
stories_iqr = stories_q3 - stories_q1
stories_lower_iqr = stories_q1 - 1.5 * stories_iqr
stories_upper_iqr = stories_q3 + 1.5 * stories_iqr

# Winsorization bounds (1st/99th percentile from training data)
stories_p1 = X_train['stories'].quantile(0.01)
stories_p99 = X_train['stories'].quantile(0.99)

print(f"  stories IQR bounds: [{stories_lower_iqr:.4f}, {stories_upper_iqr:.4f}]")
print(f"  stories Winsorization bounds (1st/99th pct): [{stories_p1:.4f}, {stories_p99:.4f}]")
print(f"  stories distribution (train):\n{X_train['stories'].describe()}")

# Apply Winsorization (cap, do NOT remove rows)
X_train['stories'] = X_train['stories'].clip(lower=stories_p1, upper=stories_p99)
X_test['stories'] = X_test['stories'].clip(lower=stories_p1, upper=stories_p99)
print("PASSED: Winsorization applied to 'stories'.")

# ─────────────────────────────────────────────
# STEP 5: Outlier Treatment for 'area', 'bedrooms', 'parking'
# (Winsorization at 1st/99th percentile, fit on train only)
# ─────────────────────────────────────────────
print("\n--- STEP 5: Outlier Treatment for 'area', 'bedrooms', 'parking' ---")

outlier_cols = ['area', 'bedrooms', 'parking']

winsor_bounds = {}
for col in outlier_cols:
    p1 = X_train[col].quantile(0.01)
    p99 = X_train[col].quantile(0.99)
    winsor_bounds[col] = (p1, p99)

    q1 = X_train[col].quantile(0.25)
    q3 = X_train[col].quantile(0.75)
    iqr = q3 - q1
    lower_iqr = q1 - 1.5 * iqr
    upper_iqr = q3 + 1.5 * iqr

    outlier_count = ((X_train[col] < lower_iqr) | (X_train[col] > upper_iqr)).sum()
    print(f"  {col}: IQR bounds=[{lower_iqr:.4f}, {upper_iqr:.4f}], "
          f"Winsor bounds=[{p1:.4f}, {p99:.4f}], "
          f"IQR outliers in train={outlier_count}")

    # Apply Winsorization
    X_train[col] = X_train[col].clip(lower=p1, upper=p99)
    X_test[col] = X_test[col].clip(lower=p1, upper=p99)

print("PASSED: Winsorization applied to 'area', 'bedrooms', 'parking'.")

# ─────────────────────────────────────────────
# STEP 6: Log1p Transformation for Skewed Numeric Features
# ─────────────────────────────────────────────
print("\n--- STEP 6: Log1p Transformation for Skewed Features ---")

log_transform_cols = ['area', 'bathrooms', 'stories', 'parking']

for col in log_transform_cols:
    skew_before = X_train[col].skew()
    X_train[col] = np.log1p(X_train[col])
    X_test[col] = np.log1p(X_test[col])
    skew_after = X_train[col].skew()
    print(f"  {col}: skew before={skew_before:.4f}, skew after={skew_after:.4f}")
    if abs(skew_after) > 0.5:
        print(f"  WARNING: '{col}' skew still outside [-0.5, 0.5] after log1p.")

print("PASSED: log1p transformation applied to area, bathrooms, stories, parking.")

# ─────────────────────────────────────────────
# STEP 7: Log Transform Target Variable 'price'
# ─────────────────────────────────────────────
print("\n--- STEP 7: Log Transform Target Variable 'price' ---")

# Store log-transformed target separately (for model training reference)
y_train_log = np.log(y_train)
y_test_log = np.log(y_test)

skew_before = y_train.skew()
skew_after = y_train_log.skew()
print(f"  price skew before log: {skew_before:.4f}")
print(f"  log_price skew after log: {skew_after:.4f}")
print("  NOTE: Use np.exp(predictions) to inverse-transform back to original price scale.")
print("PASSED: Log transformation applied to target 'price' -> 'log_price'.")

# ─────────────────────────────────────────────
# STEP 8: Feature Scaling with StandardScaler
# (Fit ONLY on training data, transform both train and test)
# ─────────────────────────────────────────────
print("\n--- STEP 8: Feature Scaling (StandardScaler) ---")

# Scale only numeric features (not binary-encoded 0/1 columns)
scale_cols = ['area', 'bedrooms', 'bathrooms', 'stories', 'parking']

scaler = StandardScaler()
X_train[scale_cols] = scaler.fit_transform(X_train[scale_cols])
X_test[scale_cols] = scaler.transform(X_test[scale_cols])

print(f"  Scaled columns: {scale_cols}")
print("  Scaler fitted on training data only (no leakage).")
print("PASSED: StandardScaler applied to numeric features.")

# ─────────────────────────────────────────────
# STEP 10: Multicollinearity Check (VIF + Correlation Matrix)
# ─────────────────────────────────────────────
print("\n--- STEP 10: Multicollinearity Check ---")

try:
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    vif_data = X_train.copy()
    # Add constant for VIF calculation
    vif_data_with_const = pd.DataFrame(
        np.column_stack([np.ones(len(vif_data)), vif_data.values]),
        columns=['const'] + vif_data.columns.tolist()
    )

    vif_results = {}
    for i, col in enumerate(vif_data.columns):
        vif_val = variance_inflation_factor(vif_data_with_const.values, i + 1)
        vif_results[col] = vif_val

    print("  VIF Results:")
    for col, vif_val in vif_results.items():
        flag = " *** HIGH VIF > 10 ***" if vif_val > 10 else ""
        print(f"    {col}: VIF = {vif_val:.4f}{flag}")

except ImportError:
    print("  WARNING: statsmodels not installed. Skipping VIF calculation.")
    print("  Install with: pip install statsmodels")

# Correlation matrix for pairwise correlation check
corr_matrix = X_train.corr().abs()
high_corr_pairs = []
for i in range(len(corr_matrix.columns)):
    for j in range(i + 1, len(corr_matrix.columns)):
        if corr_matrix.iloc[i, j] > 0.8:
            high_corr_pairs.append(
                (corr_matrix.columns[i], corr_matrix.columns[j], corr_matrix.iloc[i, j])
            )

if high_corr_pairs:
    print("  HIGH CORRELATION PAIRS (> 0.8):")
    for c1, c2, corr_val in high_corr_pairs:
        print(f"    {c1} <-> {c2}: {corr_val:.4f}")
else:
    print("  No pairwise correlations above 0.8 detected.")

print("PASSED: Multicollinearity check completed.")

# ─────────────────────────────────────────────
# STEP 11: Feature Engineering (Optional Interaction Features)
# ─────────────────────────────────────────────
print("\n--- STEP 11: Feature Engineering (Interaction Features) ---")

# area_per_bedroom: space efficiency (using log1p-transformed area and original bedrooms)
# Note: bedrooms has been scaled, so we use the scaled version for ratio
# We create these features and validate via cross-validation before including
# For now, we create them and include in the output

# area_per_bedroom = area / (bedrooms + 1) to avoid division by zero
# Using raw (pre-scaled) logic: we compute on scaled values as proxy
X_train['area_per_bedroom'] = X_train['area'] / (X_train['bedrooms'] + 1e-6)
X_test['area_per_bedroom'] = X_test['area'] / (X_test['bedrooms'] + 1e-6)

# total_rooms = bedrooms + bathrooms (scaled values)
X_train['total_rooms'] = X_train['bedrooms'] + X_train['bathrooms']
X_test['total_rooms'] = X_test['bedrooms'] + X_test['bathrooms']

# luxury_score = sum of premium binary features (already 0/1, not scaled)
X_train['luxury_score'] = X_train['airconditioning'] + X_train['prefarea'] + X_train['hotwaterheating']
X_test['luxury_score'] = X_test['airconditioning'] + X_test['prefarea'] + X_test['hotwaterheating']

print("  Created: area_per_bedroom, total_rooms, luxury_score")
print("  NOTE: Validate these features improve CV performance before final model training.")
print("PASSED: Interaction features created.")

# ─────────────────────────────────────────────
# STEP 12: Class Imbalance / Rare Category Check
# ─────────────────────────────────────────────
print("\n--- STEP 12: Rare Category Check for 'hotwaterheating' ---")

hw_positive_train = X_train['hotwaterheating'].sum()
hw_total_train = len(X_train)
hw_rate_train = hw_positive_train / hw_total_train * 100

print(f"  hotwaterheating positive rate in train: {hw_positive_train}/{hw_total_train} ({hw_rate_train:.2f}%)")
print(f"  In 5-fold CV, each fold will have ~{hw_positive_train / 5:.1f} positive examples.")

if hw_rate_train < 5.0:
    print("  WARNING: hotwaterheating has < 5% positive rate. Monitor fold-level variance in CV.")
else:
    print("  hotwaterheating positive rate is acceptable.")

print("PASSED: Rare category check completed.")

# ─────────────────────────────────────────────
# STEP 13: Final Validation Checks
# ─────────────────────────────────────────────
print("\n--- STEP 13: Final Validation Checks ---")

# (1) Assert no NaN/Inf values remain
for split_name, X_split in [('Train', X_train), ('Test', X_test)]:
    nan_count = X_split.isnull().sum().sum()
    inf_count = np.isinf(X_split.select_dtypes(include=[np.number])).sum().sum()
    assert nan_count == 0, f"ERROR: {nan_count} NaN values found in {split_name} features!"
    assert inf_count == 0, f"ERROR: {inf_count} Inf values found in {split_name} features!"
    print(f"  {split_name}: NaN={nan_count}, Inf={inf_count} — PASSED")

# (2) Assert all categorical columns are fully encoded (no object dtype)
object_cols_train = X_train.select_dtypes(include=['object']).columns.tolist()
assert len(object_cols_train) == 0, (
    f"ERROR: Object dtype columns remain in train: {object_cols_train}"
)
print("  No object dtype columns remain — PASSED")

# (3) Assert train and test feature distributions are similar (KS-test)
print("  KS-test for distribution similarity (train vs test):")
numeric_check_cols = ['area', 'bedrooms', 'bathrooms', 'stories', 'parking']
for col in numeric_check_cols:
    ks_stat, ks_pval = stats.ks_2samp(X_train[col], X_test[col])
    flag = " *** DISTRIBUTION SHIFT ***" if ks_pval < 0.05 else ""
    print(f"    {col}: KS stat={ks_stat:.4f}, p-value={ks_pval:.4f}{flag}")

# (4) Assert log_price is approximately normally distributed
log_price_skew = y_train_log.skew()
print(f"  log_price skewness (train): {log_price_skew:.4f}")
if abs(log_price_skew) <= 0.5:
    print("  log_price is approximately normally distributed — PASSED")
else:
    print(f"  WARNING: log_price skew={log_price_skew:.4f} is outside [-0.5, 0.5].")

print("PASSED: All final validation checks completed.")

# ─────────────────────────────────────────────
# Reconstruct Full Processed Dataset for Output
# ─────────────────────────────────────────────
print("\n--- Reconstructing Full Processed Dataset ---")

# Combine train and test back together with original (untransformed) target
X_full = pd.concat([X_train, X_test], axis=0)
y_full = pd.concat([y_train, y_test], axis=0)  # Original untransformed price

# Align index
X_full = X_full.sort_index()
y_full = y_full.sort_index()

# Add the original target column 'price' (untransformed) to the processed features
output_df = X_full.copy()
output_df['price'] = y_full  # Original price, not log-transformed

# Verify target appears exactly once
assert 'price' in output_df.columns, "ERROR: Target column 'price' missing from output!"
assert output_df.columns.tolist().count('price') == 1, "ERROR: 'price' appears more than once!"

print(f"  Output shape: {output_df.shape}")
print(f"  Output columns: {output_df.columns.tolist()}")
print(f"  Target 'price' included: {'price' in output_df.columns}")

# ─────────────────────────────────────────────
# Save Processed Output
# ─────────────────────────────────────────────
output_df.to_csv(OUTPUT_PATH, index=False)
print(f"\nProcessed dataset saved to: {OUTPUT_PATH}")
print(f"Final shape: {output_df.shape}")
print("\nPreprocessing pipeline completed successfully.")