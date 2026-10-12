#!/bin/bash
# Verifier entrypoint, run in the separate verifier container with the evidence Harbor
# restored at its original paths: /logs/agent/*.json and /tmp/world/*.json.
# A verifier that fails writes no reward: Harbor then records a verifier error, never a
# zero the agent did not earn.
set -uo pipefail
mkdir -p /logs/verifier
python3 /tests/grade.py
rc=$?
if [ $rc -ne 0 ]; then
  rm -f /logs/verifier/reward.json
  echo "verifier failed (rc=$rc); no reward written" >&2
  exit $rc
fi
