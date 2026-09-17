"""Fail-closed CF-120 evidence. No application imports or provider credentials."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Windows scanners/indexers can hold a just-written file for a moment; a
    # bounded retry keeps the replace atomic instead of crashing the session.
    for attempt in range(40):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.25)


def file_digest(paths, root=None):
    """Checkout-independent: names are hashed relative to root when one is given."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        name = path.relative_to(root) if root is not None else path
        digest.update(name.as_posix().encode('utf-8'))
        digest.update(path.read_bytes())
    return digest.hexdigest()


SOURCE_DIRECTORIES = ('contract', 'common', 'generator', 'verifier', 'publisher', 'vault', 'reader',
                      'librarian', 'analyst', 'console', 'scripts', 'tests', 'evaluation')
SOURCE_CONFIGS = ('scripts/http_logging.json', 'pytest.ini', '.env.example', 'pyproject.toml',
                  'uv.lock', 'poetry.lock', 'Pipfile', 'Pipfile.lock', 'setup.cfg', 'tox.ini')


def source_files_digest(root):
    """Code, inventory and frozen OpenAPI the run depends on; compared again after the run."""
    root = Path(root)
    paths = [path for directory in SOURCE_DIRECTORIES for path in (root / directory).rglob('*.py')]
    paths += list((root / 'contract').glob('*.json')) + list((root / 'docs' / 'openapi').glob('*.json'))
    paths += [root / name for name in SOURCE_CONFIGS if (root / name).is_file()]
    for pattern in ('requirements*.txt', 'requirements*.in', 'requirements*.lock', 'constraints*.txt'):
        paths.extend(root.glob(pattern))
    # Deliberately exclude local .env and credentials. Only committed examples
    # and dependency/test configuration are part of the shareable fingerprint.
    return file_digest({path for path in paths if '__pycache__' not in path.parts}, root)


def initial_evidence(root, run_id):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL)
    packages = {}
    for name in ('pytest', 'fastapi', 'pydantic', 'uvicorn', 'openai', 'httpx',
                 'sentence-transformers', 'python-docx', 'reportlab', 'pdfplumber'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = 'not-installed'
    status = git('status', '--porcelain', '--untracked-files=all')
    return {
        'kind': 'cf120-http-contract', 'schema_version': 1, 'run_id': run_id,
        'started_at': now(), 'source': {
            'commit': git('rev-parse', 'HEAD').decode('utf-8').strip(),
            'working_tree_dirty': bool(status.strip()),
            'diff_sha256': hashlib.sha256(git('diff', 'HEAD', '--binary') + status).hexdigest(),
            'files_sha256': source_files_digest(root),
        },
        'environment': {'python': sys.version.split()[0], 'packages': packages,
                        'fixture_sha256': file_digest((root / 'contract' / 'fixtures').rglob('*.py'), root)},
        'provider': {'type': 'synthetic-http', 'real_model': False},
        'mesh': {}, 'results': [], 'failures': [], 'selection': {},
        'execution_complete': False, 'contract_conformant': False,
        'acceptance_ready': False, 'release_eligible': False,
        'pytest_exit_code': None, 'cleanup': {'complete': False},
    }


def conclude(evidence, session, exit_code, manifest):
    """An assigned failure, skipped mandatory case, or empty run is never green."""
    expected = set(manifest['cases'])
    collected = set(session.get('collected', []))
    metadata_keys = ('owner', 'requirement', 'boundary', 'assertion')

    def with_metadata(item):
        metadata = {**manifest['cases'].get(item.get('nodeid'), {}),
                    **session.get('metadata', {}).get(item.get('nodeid'), {})}
        return {**item, **{key: metadata[key] for key in metadata_keys if key in metadata}}

    results = [with_metadata(item) for item in session.get('results', [])]
    by_id = {item['nodeid']: item for item in results}
    missing = sorted(expected - collected)
    unexpected = sorted(collected - expected)
    evidence['selection'] = {'expected_case_ids': sorted(expected),
                             'collected_case_ids': sorted(collected),
                             'missing_case_ids': missing, 'unexpected_case_ids': unexpected}
    evidence['results'] = results
    evidence['pytest_exit_code'] = exit_code
    evidence['failures'] = [with_metadata(item) for item in session.get('errors', [])] + [
        {**item, 'owner': item.get('owner', 'unassigned')}
        for item in results if item['outcome'] != 'passed'
    ]
    complete = bool(expected) and not missing and not unexpected and expected <= by_id.keys()
    complete = complete and session.get('session_finished') is True
    conformant = (complete and exit_code == 0 and not evidence['failures']
                  and all(by_id[key]['outcome'] == 'passed' for key in expected)
                  and evidence.get('preflight_complete') is True
                  and evidence['cleanup'].get('complete') is True
                  and not evidence.get('error'))
    evidence.update(execution_complete=bool(complete), contract_conformant=bool(conformant),
                    acceptance_ready=bool(conformant and not evidence['source']['working_tree_dirty']),
                    release_eligible=False, finished_at=now())
    return 0 if conformant else 2
