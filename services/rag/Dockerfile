FROM python:3.13-slim

WORKDIR /app

COPY requirements-rag.lock /app/requirements-rag.lock
RUN pip install --no-cache-dir --require-hashes -r requirements-rag.lock

COPY packages/common /app/packages/common
COPY services/rag /app/services/rag

ENV PYTHONPATH="/app:/app/packages/common/src:/app/services/rag"

EXPOSE 8003

CMD ["uvicorn", "services.rag.main:app", "--host", "0.0.0.0", "--port", "8003"]
