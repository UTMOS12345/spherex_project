# PARAMOST SPHEREx Flipbook as a container.
#   docker build -t paramost .
#   docker run -p 8501:8501 -v paramost-cache:/data/cache paramost
# then open http://localhost:8501. Downloads and saved results stay in the volume.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    SPHEREX_CACHE=/data/cache \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

RUN useradd --create-home --uid 1000 paramost \
    && mkdir -p /data/cache /app \
    && chown paramost:paramost /data/cache

WORKDIR /app
# the exact versions the server uses (requirements.txt), then the package itself
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY pyproject.toml README.md ./
COPY paramost ./paramost
COPY spherex ./spherex
RUN pip install --no-deps . && rm -rf /app/build

USER paramost
VOLUME ["/data/cache"]
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)" || exit 1
CMD ["paramost", "--no-browser", "--port", "8501", "--address", "0.0.0.0"]
