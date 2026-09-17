"""The frozen CF-120 inventory must equal what the contract suite actually collects."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def isolated_env(**extra):
    env = {key: value for key, value in os.environ.items() if not key.startswith(('CF120_', 'PYTEST_'))}
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', **extra)
    return env


@pytest.fixture(scope='module')
def collected(tmp_path_factory):
    target = tmp_path_factory.mktemp('cf120-inventory') / 'cases.json'
    result = subprocess.run([sys.executable, '-B', '-m', 'pytest', 'contract', '--collect-only', '-q',
                             '-p', 'no:cacheprovider'], cwd=ROOT, env=isolated_env(CF120_INVENTORY_OUT=str(target)),
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return json.loads(target.read_text(encoding='utf-8'))['cases']


def test_frozen_inventory_matches_collection_and_every_case_is_owned(collected):
    frozen = json.loads((ROOT / 'contract' / 'cases.json').read_text(encoding='utf-8'))
    assert frozen['kind'] == 'cf120-contract-inventory'
    # Regenerate with: python scripts/contract_mesh.py --freeze-inventory (then review the diff).
    assert frozen['cases'] == collected
    for nodeid, metadata in collected.items():
        assert all(metadata.get(key) for key in ('owner', 'requirement', 'boundary', 'assertion')), nodeid


def test_contract_suite_refuses_to_run_without_an_owned_manifest():
    result = subprocess.run([sys.executable, '-B', '-m', 'pytest', 'contract', '-q', '-p', 'no:cacheprovider'],
                            cwd=ROOT, env=isolated_env(), capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=300)
    assert result.returncode != 0
    assert 'contract_mesh.py' in result.stdout + result.stderr


def test_matrix_covers_every_language_and_publication_without_cartesian_growth(collected):
    from contract.fixtures.cases import EVALUATION_IDS, LANGUAGES, PUBLICATIONS
    clean = [nodeid.split('[', 1)[1].rstrip(']') for nodeid in collected
             if '::test_clean_pipeline[' in nodeid]
    assert len(clean) == len(EVALUATION_IDS) * len(LANGUAGES) == 36
    for record_id in EVALUATION_IDS:
        assert {language for language in LANGUAGES
                if f'{record_id}-{language}' in clean} == set(LANGUAGES)
    from contract.test_pipeline import FORMATS
    assert tuple(FORMATS) == PUBLICATIONS
    combinations = Counter((language, *FORMATS[EVALUATION_IDS.index(record_id) % len(FORMATS)])
                           for record_id in EVALUATION_IDS for language in LANGUAGES
                           if f'{record_id}-{language}' in clean)
    assert set(combinations) == {(language, *publication) for language in LANGUAGES for publication in PUBLICATIONS}
    poisons = [nodeid for nodeid in collected if '::test_poison_blocks_without_artifact[' in nodeid]
    assert len(poisons) == 7 * len(LANGUAGES)
