#!/usr/bin/env bash
# Runs once, when the codespace is created.
#
# Deliberately does NOT start DataHub. `datahub docker quickstart` pulls several
# GB and takes minutes; that belongs in a command you run knowingly, not in a
# hook that makes codespace creation look hung. Run ./scripts/setup.sh for that.
set -euo pipefail

say() { printf '\n\033[1;35m==>\033[0m \033[1m%s\033[0m\n' "$1"; }

say "Installing Kestrel (editable, with the agent extra)"
python -m pip install --upgrade pip >/dev/null
python -m pip install -e ".[agent,dev]"

say "Installing the DataHub CLI"
python -m pip install --upgrade acryl-datahub

say "Raising vm.max_map_count for OpenSearch"
# DataHub's search backend refuses to start under the default 65530 with
# "max virtual memory areas vm.max_map_count [65530] is too low". The
# docker-in-docker daemon is privileged, so this usually takes; if it doesn't,
# the failure surfaces later as an OpenSearch container in a crash loop.
if sudo sysctl -w vm.max_map_count=262144 >/dev/null 2>&1; then
  echo "  vm.max_map_count=262144"
else
  echo "  could not set it -- if OpenSearch crash-loops on quickstart, this is why"
fi

say "Verifying the offline path"
# Proves the toolchain is sound before DataHub is anywhere in the picture.
python -m pytest -q || echo "  (tests failed -- worth reading before going further)"

cat <<'EOF'

Ready. The offline path works now, with no DataHub:

  kestrel scan                 # the bundled fixture graph
  kestrel scan --ask "..."     # the agentic engine (needs ANTHROPIC_API_KEY)

To bring up a real DataHub in this codespace (several GB, a few minutes):

  ./scripts/setup.sh
  kestrel doctor               # what the live MCP server actually exposes
  kestrel scan --live          # read-only
  kestrel scan --live --write  # apply the write-back

The DataHub UI lands on forwarded port 9002; get a token from
Settings -> Access Tokens and `export DATAHUB_GMS_TOKEN=<token>`.

EOF
