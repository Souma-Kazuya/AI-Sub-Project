#!/usr/bin/env bash
# Script to launch QA & Boundary Synthesizer Web Dashboard
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

echo "🚀 Starting Automated QA & Boundary-Value Test Synthesizer Application..."
exec $PYTHON Main.py serve --host 127.0.0.1 --port 8000

