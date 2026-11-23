#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# Record the CLI location so the Plasma user service can find it too.
codex_path=$(type -P codex || true)
if [[ -n "$codex_path" ]]; then
    if [[ ! "$codex_path" -ef .venv/bin/codex ]]; then
        ln -sfn "$(realpath "$codex_path")" .venv/bin/codex
    fi
else
    if ! command -v npm >/dev/null; then
        echo 'Install npm (Arch: sudo pacman -S npm) or install the Codex CLI, then rerun ./install.sh.' >&2
        exit 1
    fi
    read -r codex_package < requirements-npm.txt
    npm install --prefix .venv --no-save --no-package-lock "$codex_package"
    ln -sfn ../node_modules/.bin/codex .venv/bin/codex
fi
.venv/bin/codex --version
