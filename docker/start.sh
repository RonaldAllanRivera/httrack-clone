#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=${DISPLAY:-:99}
export HTCLONE_DOWNLOAD_ROOT=${HTCLONE_DOWNLOAD_ROOT:-/downloads}

# Start virtual X display
Xvfb "$DISPLAY" -screen 0 "${XVFB_RESOLUTION:-1280x800x24}" -ac +extension GLX +render -noreset &

# Lightweight window manager (keeps Tk windows manageable)
fluxbox &

# VNC server (no password; intended for localhost access via mapped ports)
x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 &

# noVNC web proxy (Ubuntu package doesn't ship novnc_proxy)
# Serve the noVNC static files and proxy websocket traffic to VNC.
websockify --web=/usr/share/novnc 6080 localhost:5900 &

# Launch the Tkinter GUI
exec python3 -m app.main
