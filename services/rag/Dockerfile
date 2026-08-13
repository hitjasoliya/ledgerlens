FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt pydantic-settings

COPY packages/common /app/packages/common
COPY services/rag /app/services/rag

ENV PYTHONPATH="/app/packages/common/src:/app/services/rag"

EXPOSE 8003

CMD ["uvicorn", "services.rag.main:app", "--host", "0.0.0.0", "--port", "8003"]
