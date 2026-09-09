FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY voice_ai ./voice_ai

RUN pip install --no-cache-dir .

RUN useradd --create-home via && mkdir -p /data && chown via:via /data
USER via

ENV VIA_DB=/data/via.db
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status==200 else 1)"

CMD ["python", "-m", "voice_ai.main", "serve", "--port", "8080", "--db", "/data/via.db"]
