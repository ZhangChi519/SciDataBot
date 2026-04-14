#!/bin/bash
# scidatabot launcher

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    echo "Please run: python3 -m venv .venv"
    exit 1
fi

# Set PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR/src"

# Default command is tui if no arguments provided
if [ $# -eq 0 ]; then
    exec "$VENV_PYTHON" -c "from src.cli import app; app()" -- tui
else
    exec "$VENV_PYTHON" -c "from src.cli import app; app()" -- "$@"
fi
