#!/usr/bin/env bash
# Bring up everything Kestrel needs for a live run.
#
#   ./scripts/setup.sh          # quickstart + datapack + install + smoke check
#   ./scripts/setup.sh --skip-datahub   # if DataHub is already running
#
# Nothing here is destructive except `datahub docker quickstart`, which starts
# containers on your machine. Read it before you run it.
set -euo pipefail

SKIP_DATAHUB=0
[[ "${1:-}" == "--skip-datahub" ]] && SKIP_DATAHUB=1

say() { printf '\n\033[1;35m==>\033[0m \033[1m%s\033[0m\n' "$1"; }

say "Installing Kestrel"
python -m pip install --upgrade pip >/dev/null
python -m pip install -e ".[agent]"

if [[ $SKIP_DATAHUB -eq 0 ]]; then
  say "Installing the DataHub CLI"
  python -m pip install --upgrade acryl-datahub

  say "Starting DataHub (this pulls containers the first time -- give it a few minutes)"
  datahub docker quickstart

  say "Loading sample data"
  # showcase-ecommerce gives a broad graph; healthcare plants the PII and
  # quality issues the demo policies are written against.
  datahub datapack load showcase-ecommerce || echo "  (datapack load failed -- load one manually)"
fi

say "Environment"
export DATAHUB_GMS_URL="${DATAHUB_GMS_URL:-http://localhost:8080}"
export TOOLS_IS_MUTATION_ENABLED=true
echo "  DATAHUB_GMS_URL=$DATAHUB_GMS_URL"
echo "  TOOLS_IS_MUTATION_ENABLED=true   <- without this the write tools stay hidden"
if [[ -z "${DATAHUB_GMS_TOKEN:-}" ]]; then
  echo
  echo "  DATAHUB_GMS_TOKEN is not set. Create one in the DataHub UI under"
  echo "  Settings -> Access Tokens, then: export DATAHUB_GMS_TOKEN=<token>"
fi

say "Registering the structured property Kestrel writes"
if command -v datahub >/dev/null 2>&1; then
  datahub properties upsert -f scripts/structured_properties.yaml \
    || echo "  (registration failed -- the tag and document layers still work; see scripts/structured_properties.yaml)"
fi

say "Smoke check"
python scripts/smoke_check.py || true

cat <<'EOF'

Next:
  kestrel scan                 # offline, against the bundled fixture graph
  kestrel doctor               # what the live MCP server exposes
  kestrel scan --live          # read-only run against DataHub
  kestrel scan --live --write  # apply the write-back

EOF
