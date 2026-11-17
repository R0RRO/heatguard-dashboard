FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HG_DB_PATH=/app/data/heatguard.sqlite \
    HG_ENABLE_DEMO=0

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir ".[api,wbgt]" \
    && groupadd --system heatguard \
    && useradd --system --gid heatguard --home /app heatguard \
    && mkdir -p /app/data \
    && chown -R heatguard:heatguard /app/data

USER heatguard
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "heatguard.api:app", "--host", "0.0.0.0", "--port", "8000"]

