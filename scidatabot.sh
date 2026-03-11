#!/bin/bash
# scidatabot launcher

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    echo "Please run: python3.12 -m venv .venv"
    exit 1
fi

# Check for --tui flag
if [[ "$1" == "--tui" || "$1" == "-t" ]]; then
    shift
    exec "$VENV_PYTHON" "$SCRIPT_DIR/tui.py" "$@"
else
    exec "$VENV_PYTHON" -m src.main "$@"
fi
