# Quick Start Guide

## 🚀 Run Everything in 3 Steps

### Prerequisites
```powershell
# 1. Start Ollama (if not running)
ollama serve

# 2. Pull a model (if needed)
ollama pull phi4
```

---

## Step 1: Generate Dataset Report

```powershell
cd "Pre Processing Agent"
python report_generator.py --csv "../Datasets/Housing.csv" --target "price" --output "../Housing.json"
cd ..
```

**Output**: `Housing.json` (dataset analysis report)

---

## Step 2: Train Models (Uses Report Directly)

```powershell
cd "Reasoning Agent"

# Train models (complete pipeline - uses Pre Processing report directly)
python -m src.main train-models "../housing report.json" "../Datasets/Housing.csv" ^
  --test-size 0.2

cd ..
```

**Output**: 
- `generated_code/Housing_validate_models.py` (validation code)
- `generated_code/Housing_deploy_best_model.py` (deployment code)

**Note**: No metadata generation needed! The Reasoning Agent uses the Pre Processing Agent report directly.

---

## Step 3: Run Generated Code

```powershell
cd "Reasoning Agent"
python generated_code/Housing_validate_models.py
```

---

## 📋 For Different Datasets

### Housing Dataset (Regression)
```powershell
# Step 1
cd "Pre Processing Agent"
python report_generator.py --csv "../Datasets/Housing.csv" --target "price" --output "../Housing.json"
cd ..

# Step 2
cd "Reasoning Agent"
python -m src.main train-models "../Housing.json" "../Datasets/Housing.csv" --test-size 0.2
cd ..
```

### AAPL Dataset (Classification)
```powershell
# Step 1
cd "Pre Processing Agent"
python report_generator.py --csv "../Datasets/AAPL.csv" --target "Day" --output "../AAPL.json"
cd ..

# Step 2
cd "Reasoning Agent"
python -m src.main train-models "../AAPL.json" "../Datasets/AAPL.csv" --test-size 0.2
cd ..
```

---

## 📁 Output Files Structure

```
IntelliModel/
├── Housing.json                          # Dataset report (from Pre Processing Agent)
├── AAPL.json                             # Dataset report (from Pre Processing Agent)
├── Datasets/
│   ├── Housing.csv
│   ├── AAPL.csv
│   └── ...
└── Reasoning Agent/
    └── generated_code/
        ├── Housing_validate_models.py    # Validation code
        ├── Housing_deploy_best_model.py  # Deployment code
        ├── AAPL_validate_models.py      # Validation code
        └── AAPL_deploy_best_model.py    # Deployment code
```

---

## ⚡ One-Liner (After Setup)

```powershell
# For Housing dataset
cd "Pre Processing Agent" && python report_generator.py --csv "../Datasets/Housing.csv" --target "price" --output "../Housing.json" && cd .. && cd "Reasoning Agent" && python -m src.main train-models "../Housing.json" "../Datasets/Housing.csv" --test-size 0.2 && cd ..
```

---

## 🔧 Troubleshooting

**Ollama not running?**
```powershell
ollama serve
```

**Missing dependencies?**
```powershell
cd "Pre Processing Agent" && pip install -r requirements.txt && cd ..
cd "Reasoning Agent" && pip install -r requirements.txt && cd ..
```

**File not found?**
- Make sure you're in the correct directory
- Check that dataset files exist in `Datasets/` folder
- Use relative paths: `../Datasets/Housing.csv`

---

For detailed documentation, see `COMPLETE_WORKFLOW_GUIDE.md`

