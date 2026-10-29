#!/usr/bin/env bash
# Launch the Streamlit dashboard.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
exec streamlit run jobhunt/ui.py "$@"
