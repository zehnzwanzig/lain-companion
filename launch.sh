#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# Wayland compositors, including KWin, decide the initial location of ordinary
# top-level windows and may ignore QWidget.move() during pointer dragging.
# Run the Qt app via XWayland for Clippy-style absolute positioning. This does
# not change your Plasma session from Wayland to X11.
if [[ "${XDG_SESSION_TYPE:-}" == "wayland" && -z "${QT_QPA_PLATFORM:-}" ]]; then
  export QT_QPA_PLATFORM=xcb
fi

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python main.py
fi
exec python main.py
