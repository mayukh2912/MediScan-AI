# Build from the repository root:  docker build -f backend/Dockerfile -t mediscan-api .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
# CPU-only PyTorch keeps the image ~1.5 GB smaller than the default CUDA wheel
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r backend/requirements.txt

COPY backend backend
COPY ml ml
COPY models models
COPY reports/figures reports/figures

RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app /app /data
USER app
ENV MEDISCAN_STORAGE_DIR=/data/storage PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health')"
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
