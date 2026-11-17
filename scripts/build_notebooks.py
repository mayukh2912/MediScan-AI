"""Builds and executes the EDA notebooks (outputs are real results on the local datasets)."""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks"
NB.mkdir(exist_ok=True)


def nb(cells):
    n = nbf.v4.new_notebook()
    n.cells = [nbf.v4.new_markdown_cell(c[1]) if c[0] == "md" else nbf.v4.new_code_cell(c[1]) for c in cells]
    n.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    return n


SETUP = "import sys, os\nsys.path.insert(0, os.path.abspath('..'))\nimport numpy as np, pandas as pd\nimport matplotlib.pyplot as plt\npd.set_option('display.width', 140)"

liver = nb([
    ("md", "# Liver EDA – Indian Liver Patient Dataset (ILPD)\nSchema validation, missingness, class balance, distributions and correlations. "
           "Label `Dataset`: 1 = record from a liver patient, 2 = non-patient (dataset authors' definition, not a diagnosis)."),
    ("code", SETUP + "\nfrom ml.liver.data import load_ilpd, validate_ilpd\ndf = load_ilpd('../datasets/liver/indian_liver_patient.csv')\ndf.head()"),
    ("code", "rep = validate_ilpd(df); rep.as_dict()"),
    ("code", "df.describe().T"),
    ("code", "df['Dataset'].value_counts().rename({1:'liver patient',2:'non-patient'})"),
    ("md", "## Skewed enzyme distributions (log scale)"),
    ("code", "cols=['Total_Bilirubin','Direct_Bilirubin','Alkaline_Phosphotase','Alamine_Aminotransferase','Aspartate_Aminotransferase']\nfig,ax=plt.subplots(1,5,figsize=(18,3))\nfor a,c in zip(ax,cols):\n    for lab,g in df.groupby('Dataset'): a.hist(np.log1p(g[c]),bins=30,alpha=.6,label={1:'patient',2:'non-patient'}[lab])\n    a.set_title('log1p '+c,fontsize=8)\nax[0].legend(); plt.tight_layout()"),
    ("code", "df.drop(columns=['Gender']).corr(method='spearman').round(2)"),
    ("md", "Observations: strong right skew in bilirubin and enzymes (log transform used for logistic regression); "
           "TB/DB and ALT/AST are highly correlated; 4 missing A/G ratios; 13 exact duplicate rows (removed before splitting to avoid leakage); "
           "3 rows with direct > total bilirubin (kept, flagged)."),
])

ecg = nb([
    ("md", "# ECG EDA – MIT-BIH Arrhythmia Database\nVerifies record integrity, AAMI class distribution per record, and why an inter-patient split is required."),
    ("code", SETUP + "\nimport wfdb, glob, collections\nfrom ml.ecg.beat_dataset import AAMI_MAP, DS1, DS2, PACED\nrecs=sorted(os.path.basename(f)[:-4] for f in glob.glob('../datasets/mitdb/*.hea')); len(recs)"),
    ("code", "rows=[]\nfor r in recs:\n    a=wfdb.rdann(f'../datasets/mitdb/{r}','atr'); c=collections.Counter(AAMI_MAP.get(s) for s in a.symbol if s in AAMI_MAP)\n    rows.append({'record':r,'split':'DS1' if r in DS1 else 'DS2' if r in DS2 else 'paced', **c})\ncounts=pd.DataFrame(rows).fillna(0).set_index('record'); counts.groupby('split').sum()"),
    ("code", "counts[['S','V','F']].sort_values('F',ascending=False).head(10)"),
    ("md", "F beats are concentrated in a handful of records (e.g. 208 in DS1, 213 in DS2). A random beat-level split would put beats from the same "
           "patient in train and test and overstate performance – the Kaggle CSV split has this problem because it carries no record IDs."),
    ("code", "rec=wfdb.rdrecord('../datasets/mitdb/208',sampto=360*10); ann=wfdb.rdann('../datasets/mitdb/208','atr',sampto=360*10)\nplt.figure(figsize=(14,3)); plt.plot(np.arange(rec.sig_len)/360, rec.p_signal[:,0],lw=.8)\nfor s,sym in zip(ann.sample,ann.symbol): plt.text(s/360, rec.p_signal[:,0].max(), sym, fontsize=8)\nplt.title('Record 208 (MLII), first 10 s with reference beat labels'); plt.xlabel('s')"),
    ("code", "from ml.ecg.signal_processing import clean_ecg, signal_quality, detect_r_peaks\nx=wfdb.rdrecord('../datasets/mitdb/105').p_signal[:360*60,0]\nsignal_quality(clean_ecg(x,360,60),360)  # record 105 is known to be noisy"),
])

cardio = nb([
    ("md", "# Cardiovascular dataset EDA (sulianova/cardiovascular-disease-dataset)\n"
           "**Why this dataset is NOT used to train a lipid model:** its `cholesterol` column is an ordinal category "
           "(1 normal, 2 above normal, 3 well above normal) and the target `cardio` is presence of cardiovascular disease. "
           "Neither is a measured lipid value nor a labelled lipid abnormality, so the lipid module stays rule-based.\n\n"
           "Download with `scripts/download_datasets.sh`; this notebook only runs if the file is present."),
    ("code", SETUP + "\np='../datasets/cardio/cardio_train.csv'\nif os.path.exists(p):\n    d=pd.read_csv(p,sep=';'); print(d.shape); display(d.head()); display(d['cholesterol'].value_counts()); display(pd.crosstab(d['cholesterol'],d['cardio'],normalize='index'))\nelse:\n    print('Dataset not downloaded – see datasets/README.md')"),
])

for name, n in (("liver_eda.ipynb", liver), ("ecg_eda.ipynb", ecg), ("cardiovascular_eda.ipynb", cardio)):
    NotebookClient(n, timeout=600, resources={"metadata": {"path": str(NB)}}).execute()
    nbf.write(n, NB / name)
    print("executed", name)
