.PHONY: ci test smoke fuzz
ci:    ; @bash scripts/ci.sh
test:  ; @PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider
smoke: ; @for s in A B C D E F; do PYTHONPATH=src python3 selfplay_bughunt.py $$s --seed 11 --max-steps 8000; done
fuzz:  ; @PYTHONPATH=src python3 cardfx_fuzz.py --seeds 6
