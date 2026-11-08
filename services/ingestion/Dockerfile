FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fontconfig \
    fonts-liberation \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-ingestion.lock /app/requirements-ingestion.lock
RUN pip install --no-cache-dir --require-hashes -r requirements-ingestion.lock

COPY packages/common /app/packages/common
COPY services/ingestion /app/services/ingestion

ENV PYTHONPATH="/app:/app/packages/common/src:/app/services/ingestion"

EXPOSE 8002

CMD ["uvicorn", "services.ingestion.main:app", "--host", "0.0.0.0", "--port", "8002"]
