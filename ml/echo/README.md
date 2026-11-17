# ml/echo

Structured report extraction only (`backend/services/measurement_extractor.py` + `analyzers/echo.py`). No ECHO image/video model is trained or claimed: the echo2022 / Mendeley datasets were not available in the build environment. A future model must use a separate dataset and its own evaluation, registered via `ml/model_registry.save_metadata("echo", …)`.
