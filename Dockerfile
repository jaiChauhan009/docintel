# Shared image for the API and the Kafka worker.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# OCR runtime deps: tesseract engine + poppler for pdf->image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libtesseract-dev \
        poppler-utils \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN chmod +x scripts/entrypoint.sh scripts/worker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
