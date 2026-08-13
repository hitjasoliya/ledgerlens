FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt pydantic-settings

COPY packages/common /app/packages/common
COPY services/ingestion /app/services/ingestion

ENV PYTHONPATH="/app/packages/common/src:/app/services/ingestion"

EXPOSE 8002

CMD ["uvicorn", "services.ingestion.main:app", "--host", "0.0.0.0", "--port", "8002"]
