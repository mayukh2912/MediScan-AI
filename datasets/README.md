# datasets/

Raw datasets live here and are git-ignored. Download with:

```bash
pip install kaggle wfdb      # and put your Kaggle API token in ~/.kaggle/kaggle.json
bash scripts/download_datasets.sh
```

Manual alternatives:
* ILPD → https://www.kaggle.com/datasets/uciml/indian-liver-patient-records → `datasets/liver/indian_liver_patient.csv`
* MIT-BIH → `python -c "import wfdb; wfdb.dl_database('mitdb','datasets/mitdb')"` (or https://physionet.org/content/mitdb/1.0.0/)
* Kaggle heartbeat (optional) → `datasets/heartbeat/mitbih_{train,test}.csv`
* echo2022 → accept the competition rules on Kaggle, then `kaggle competitions download -c echo2022 -p datasets/echo`
* Mendeley ECHO dataset → download manually from https://data.mendeley.com/datasets/nvx2kchfyh/1 into `datasets/echo/mendeley/`

See ../docs/DATASETS.md for schemas, licences, provenance of the files used for the shipped models, and why some datasets are not used.
