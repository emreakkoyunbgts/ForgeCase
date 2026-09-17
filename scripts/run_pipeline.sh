#!/usr/bin/env bash
# HTTP pipeline. Examples:
# bash scripts/run_pipeline.sh --record-id eng-01 --language tr --approve --format pdf --out out/case.pdf
set -euo pipefail
PYTHON="${CASEFORGE_PYTHON:-python}"
exec "$PYTHON" -m integration.one_flow "$@"
