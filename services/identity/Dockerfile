FROM python:3.13-slim

WORKDIR /app

COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

COPY packages/common /app/packages/common
COPY services/identity /app/services/identity

ENV PYTHONPATH="/app/packages/common/src:/app/services/identity"

EXPOSE 8001

HEALTHCHECK --interval=5s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health')"

CMD ["uvicorn", "services.identity.main:app", "--host", "0.0.0.0", "--port", "8001"]
