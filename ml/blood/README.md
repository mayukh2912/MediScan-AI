# ml/blood

No supervised model is shipped. See docs/DATASETS.md#blood: no public dataset with independently confirmed anaemia/deficiency labels was found, and WBC-image datasets cannot inform iron/B12/folate status. The rule-based engine lives in `backend/services/analyzers/blood.py`. To add a model, follow `ml/liver/train.py` (data validation → Pipeline/ColumnTransformer → stratified CV → held-out test → SHAP → `save_metadata("blood", …)`).
