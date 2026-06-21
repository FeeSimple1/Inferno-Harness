# Continuous Integration

`github-actions-ci.yml` is a ready GitHub Actions workflow (full test suite +
six-scenario self-play smoke on Python 3.11/3.12, every push and PR).

## Enabling hosted CI (one-time)
GitHub refuses any push that adds files under `.github/workflows/` unless the
pushing token has the **`workflow`** scope. The PAT used for automated commits
here does not, so the workflow is parked at this path. To turn it on, do ONE of:

1. **Web UI (no token change):** open this repo on github.com → Add file →
   Create new file → name it `.github/workflows/ci.yml` → paste the contents of
   `ci/github-actions-ci.yml` → commit.
2. **CLI with a workflow-scoped token:** re-issue the PAT with the `workflow`
   scope, then `git mv ci/github-actions-ci.yml .github/workflows/ci.yml &&
   git commit && git push`.

## Running the same checks locally (no CI needed)
`bash scripts/ci.sh`  (or `make ci`) — runs the suite, the six-scenario
self-play smoke, and the card-effect integration fuzz; exits non-zero on any
failure. Install as a pre-push hook:

    ln -s ../../scripts/ci.sh .git/hooks/pre-push
