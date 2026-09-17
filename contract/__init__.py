"""CF-120 live HTTP contract verification.

This package is deliberately OUTSIDE `pytest.ini testpaths`: the default
`python -m pytest -q` must never require a running mesh. Run it explicitly
through `scripts/contract_mesh.py`, which prepares the environment and then
launches its own pytest subprocess.
"""
