FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app && mkdir /data && chown app /data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY stream.py ./
COPY streamer ./streamer

USER app
# state (high scores / challenge progress) and generated music live in /data -> mount a volume there
ENV PYTHONUNBUFFERED=1 PORT=8000 STATE_FILE=/data/state.json CACHE_DIR=/data/cache
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=4)"

ENTRYPOINT ["python", "-u", "stream.py"]
