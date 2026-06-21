# Continuous Integration

Hosted CI is **active**: `.github/workflows/ci.yml` runs the full test suite plus
a six-scenario self-play smoke on Python 3.11/3.12 for every push and pull
request (see the repo's **Actions** tab).

## Running the same checks locally
`bash scripts/ci.sh` (or `make ci`) runs the suite, the six-scenario self-play
smoke, and the card-effect integration fuzz; exits non-zero on any failure.
Install as a pre-push hook:

    ln -s ../../scripts/ci.sh .git/hooks/pre-push
