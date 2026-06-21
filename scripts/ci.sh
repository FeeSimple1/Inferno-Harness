#!/usr/bin/env bash
# Local CI: the same checks the GitHub Actions workflow runs. Use directly
# (`bash scripts/ci.sh`), via `make ci`, or as a git pre-push hook
# (`ln -s ../../scripts/ci.sh .git/hooks/pre-push`). Exits non-zero on failure.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src

echo "== [1/3] Test suite =="
python3 -m pytest -q -p no:cacheprovider

echo "== [2/3] Self-play smoke (six scenarios; anomalies fail) =="
for scen in A B C D E F; do
  python3 selfplay_bughunt.py "$scen" --seed 11 --max-steps 8000
done

echo "== [3/3] Card-effect integration fuzz =="
python3 cardfx_fuzz.py --seeds 6

echo "== CI OK =="
