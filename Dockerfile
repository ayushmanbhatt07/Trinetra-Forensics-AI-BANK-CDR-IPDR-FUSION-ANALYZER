# ---- backend ----
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libjpeg62-turbo libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY investigative_copilot ./investigative_copilot

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys,os; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health').status==200 else 1)"

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
