FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt pydantic-settings

COPY packages/common /app/packages/common
COPY services/identity /app/services/identity

ENV PYTHONPATH="/app/packages/common/src:/app/services/identity"

EXPOSE 8001

CMD ["uvicorn", "services.identity.main:app", "--host", "0.0.0.0", "--port", "8001"]
