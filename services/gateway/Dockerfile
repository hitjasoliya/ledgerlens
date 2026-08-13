FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt pydantic-settings httpx

COPY packages/common /app/packages/common
COPY services/gateway /app/services/gateway

ENV PYTHONPATH="/app/packages/common/src:/app/services/gateway"

EXPOSE 8000

CMD ["uvicorn", "services.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
