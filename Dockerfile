FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        bash \
        python3 \
        python3-pip \
        python3-tk \
        python3-venv \
        xvfb \
        fluxbox \
        x11vnc \
        novnc \
        websockify \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docker ./docker
COPY README.md CHANGELOG.md ./

RUN chmod +x /app/docker/start.sh

RUN mkdir -p /downloads && chown -R appuser:appuser /downloads
ENV HTCLONE_DOWNLOAD_ROOT=/downloads

USER appuser

EXPOSE 6080

CMD ["/app/docker/start.sh"]
