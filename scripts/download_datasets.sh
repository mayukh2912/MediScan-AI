#!/usr/bin/env bash
# Downloads the datasets used by MediScan AI into ./datasets.
# Requirements: `pip install kaggle wfdb` and a Kaggle API token in ~/.kaggle/kaggle.json
# (Kaggle -> Account -> Create New API Token). Read each dataset's licence before use.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p datasets/{liver,heartbeat,mitdb,cardio,blood_cells,ecg_images,echo}

echo "== Indian Liver Patient Records (UCI id 225, CC BY 4.0)"
kaggle datasets download -d uciml/indian-liver-patient-records -p datasets/liver --unzip

echo "== MIT-BIH Arrhythmia Database v1.0.0 (PhysioNet, ODC-By 1.0) – used for the inter-patient ECG model"
python - <<'PY'
import wfdb
wfdb.dl_database("mitdb", dl_dir="datasets/mitdb")
PY

echo "== ECG Heartbeat Categorization (Kaggle shayanfazeli/heartbeat) – optional intra-patient benchmark"
kaggle datasets download -d shayanfazeli/heartbeat -p datasets/heartbeat --unzip || echo "skipped"

echo "== Cardiovascular disease dataset (EDA only; see docs/DATASETS.md)"
kaggle datasets download -d sulianova/cardiovascular-disease-dataset -p datasets/cardio --unzip || echo "skipped"

echo "== Blood cell images (BCCD-derived; investigation only)"
kaggle datasets download -d paultimothymooney/blood-cells -p datasets/blood_cells --unzip || echo "skipped"

echo "== ECG images dataset dsv/19217307 (inspect licence before use)"
kaggle datasets download -d dsv/19217307 -p datasets/ecg_images --unzip || echo "skipped"

echo "== echo2022 is a Kaggle *competition*: accept its rules on the website first, then:"
echo "   kaggle competitions download -c echo2022 -p datasets/echo"
echo "Done. Verify checksums with: sha256sum datasets/liver/indian_liver_patient.csv"
