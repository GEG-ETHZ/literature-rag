#!/usr/bin/env bash
# Point a deployed Agent Engine agent at another RAG corpus by rewriting its RAG_CORPUS environment
# variable. Reversible: run again with the previous corpus name. Prints the old and new value.
#
# Usage: scripts/switch-agent-corpus.sh <reasoning engine id> <corpus resource name>
set -euo pipefail

PROJECT="${PROJECT:-geg-core-dev}"
REGION="${REGION:-europe-west1}"
ENGINE_ID="${1:?reasoning engine id}"
CORPUS="${2:?corpus resource name, projects/.../ragCorpora/...}"

BASE="https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines/${ENGINE_ID}"
TOKEN="$(gcloud auth print-access-token)"
CURRENT="$(mktemp)"
curl -sf -H "Authorization: Bearer ${TOKEN}" "${BASE}" > "${CURRENT}"

BODY="$(python3 - "${CURRENT}" "${CORPUS}" <<'PY'
import json, sys
engine = json.load(open(sys.argv[1]))
env = engine["spec"]["deploymentSpec"]["env"]
old = next(e["value"] for e in env if e["name"] == "RAG_CORPUS")
print(f"RAG_CORPUS: {old} -> {sys.argv[2]}", file=sys.stderr)
new_env = [{**e, "value": sys.argv[2]} if e["name"] == "RAG_CORPUS" else e for e in env]
print(json.dumps({"spec": {"deploymentSpec": {"env": new_env}}}))
PY
)"

curl -sf -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -X PATCH "${BASE}?updateMask=spec.deploymentSpec.env" -d "${BODY}" | python3 -c "import json,sys; print('operation:', json.load(sys.stdin).get('name'))"
rm -f "${CURRENT}"
