"""Run all CF-120 contracts on private real HTTP services; never real LLM calls."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contract.evidence import initial_evidence, save_json, conclude, source_files_digest
from contract.mesh import Mesh, SERVICES, PortBindError, addresses_for
from contract.boundary_relay import Relay
from contract.client import Client


def prepare_env(temporary, addresses):
    env = os.environ.copy()
    for name in list(env):
        if name.upper().endswith('_PROXY') or name.startswith('PYTEST_'):
            env.pop(name)
    env.update(OPENAI_API_KEY='', OPENAI_BASE_URL='', HF_HUB_OFFLINE='1',
               TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
               CASEFORGE_TOKEN='cf120-local-test-token', PYTHONUTF8='1',
               PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT),
               GENERATOR_TRANSLATION_MODEL='cf120-stub-translation',
               VERIFIER_SEMANTIC_MODEL='cf120-stub-assessment',
               CASEFORGE_VAULT_DB=str(Path(temporary) / 'vault' / 'store.db'),
               CASEFORGE_ARTIFACT_DIR=str(Path(temporary) / 'artifacts'))
    for name in SERVICES:
        env[name.upper() + '_URL'] = addresses[name]
    return env


def functional_preflight(client):
    from contract.fixtures.cases import SOURCE_01
    from tests.support import closeout_pdf
    probe = {**deepcopy(SOURCE_01), 'id': 'eng-cf120-probe'}
    result = client.request('reader', 'POST', '/extract', files={
        'document': ('cf120-probe.pdf', closeout_pdf(probe), 'application/pdf')})
    assert result.headers.get('X-Vault-Stored') == 'true', result.headers
    try:
        response = client.request('librarian', 'GET', '/search', expected=None,
                                  params={'q': 'Python payment processing', 'top': 1, 'strategy': 'dense'})
        if response.status_code != 200:
            # Requests never download weights; a missing cache is a prerequisite failure, not a skip.
            raise RuntimeError('Librarian functional readiness failed with HTTP %s. Provision the embedding '
                               'model first: python scripts/provision_librarian.py' % response.status_code)
        search = response.json()
        assert len(search['matches']) == 1 and search['matches'][0]['engagement_id'] == probe['id']
        match = client.request('librarian', 'POST', '/match', json={
            'rfp_text': 'Python payment processing', 'top_k': 1, 'strategy': 'dense',
            'min_dense_score': 0}).json()
        assert match['requirements'] and match['requirements'][0]['best_match']['engagement_id'] == probe['id']
        coverage = client.request('analyst', 'GET', '/coverage').json()
        assert coverage['total_engagements'] == 1
    finally:
        client.delete_source(probe['id'])
    assert client.request('librarian', 'GET', '/search', params={'q': 'Python', 'top': 1}).json()['matches'] == []
    assert client.request('vault', 'GET', '/engagements').json()['total'] == 0
    return {'reader_storage': True, 'librarian_embedding_search': True, 'librarian_match': True,
            'analyst_coverage': True, 'probe_removed': True}


def freeze_inventory():
    """Rewrite contract/cases.json from collection; review the diff before committing."""
    target = ROOT / 'contract' / 'cases.json'
    env = {key: value for key, value in os.environ.items() if not key.startswith('CF120_')}
    env.update(CF120_INVENTORY_OUT=str(target), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', '-m', 'pytest', 'contract', '--collect-only', '-q',
                             '-p', 'no:cacheprovider'], cwd=ROOT, env=env, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        print(result.stdout[-4000:] + result.stderr[-4000:], file=sys.stderr)
        return 2
    cases = json.loads(target.read_text(encoding='utf-8'))['cases']
    print(f'CF-120 inventory: {len(cases)} cases written to {target}', flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='out/acceptance/contract.json')
    parser.add_argument('--select', help='Developer -k selection; partial coverage cannot pass acceptance')
    parser.add_argument('--timeout', type=float, default=1800, help='Whole pytest subprocess deadline in seconds')
    parser.add_argument('--freeze-inventory', action='store_true',
                        help='Only regenerate contract/cases.json from the collected contract cases')
    args = parser.parse_args(argv)
    if args.freeze_inventory:
        return freeze_inventory()
    output = Path(args.output).resolve()
    if output.name == 'live.json' or output.suffix != '.json':
        parser.error('Use a contract .json output, never live.json')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    manifest = json.loads((ROOT / 'contract' / 'cases.json').read_text(encoding='utf-8'))
    run_id = uuid4().hex
    directory = ROOT / 'out' / 'acceptance' / 'cf120' / run_id
    directory.mkdir(parents=True)
    evidence = initial_evidence(ROOT, run_id)
    evidence['run_directory'] = str(directory)
    evidence['startup_attempts'] = []
    mesh = relay = client = child = None
    session, exit_code = {}, None
    temporary = tempfile.TemporaryDirectory(prefix='caseforge-cf120-')
    try:
        # Full-map retry handles the bind-after-reservation race before pytest imports URLs.
        for attempt in range(3):
            addresses = addresses_for((*SERVICES, 'provider'))
            env = prepare_env(temporary.name, addresses)
            os.environ.update(env)
            mesh = Mesh(directory, env, addresses)
            relay = Relay(mesh, 0, uuid4().hex)
            relay.start()
            mesh.relay_url = relay.url
            try:
                mesh.start_all()
                break
            except Exception as exc:
                cleanup = mesh.stop_all()
                evidence['startup_attempts'].append({
                    'attempt': attempt + 1, 'addresses': addresses, 'error': str(exc),
                    'retryable_bind_conflict': isinstance(exc, PortBindError), 'cleanup': cleanup,
                })
                relay.close()
                relay = None
                if not cleanup['complete'] or attempt == 2 or not isinstance(exc, PortBindError):
                    raise
        config = {'addresses': addresses, 'relay_url': relay.url,
                  'token': env['CASEFORGE_TOKEN'], 'control_token': relay.token,
                  'artifact_dir': env['CASEFORGE_ARTIFACT_DIR'], 'run_directory': str(directory)}
        config_path = directory / 'mesh-private.json'
        save_json(config_path, config)
        client = Client(config)
        evidence['mesh'] = {'services': list(SERVICES), 'addresses': addresses,
                            'health': mesh.health,
                            'functional_readiness': functional_preflight(client)}
        evidence['preflight_complete'] = True
        print('CF-120: seven real APIs ready; nonempty Librarian/Analyst probe passed.', flush=True)
        env.update(CF120_MANIFEST=str(config_path), CF120_SESSION_REPORT=str(directory / 'pytest.json'))
        command = [sys.executable, '-B', '-m', 'pytest', 'contract', '-q', '--tb=short',
                   '-p', 'no:cacheprovider', '--junitxml=' + str(directory / 'junit.xml')]
        if args.select:
            command.extend(['-k', args.select])
        with (directory / 'pytest.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                exit_code = child.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                mesh.stop_process(child)
                raise RuntimeError('Contract pytest exceeded its whole-run deadline') from None
        if (directory / 'pytest.json').exists():
            session = json.loads((directory / 'pytest.json').read_text(encoding='utf-8'))
        provider = client.provider_state()
        boundary = client.session.get(relay.url + '/__calls',
            headers={'X-CF120-Control': relay.token}, timeout=5).json()
        save_json(directory / 'provider-calls.json', provider)
        save_json(directory / 'boundary-calls.json', boundary)
        if not provider['calls'] or provider['armed_unused'] or boundary['armed_unused']:
            raise RuntimeError('Missing provider traffic or armed-but-unused faults')
        evidence['provider']['call_count'] = len(provider['calls'])
        evidence['mesh']['process_history'] = mesh.history
    except BaseException as exc:
        evidence['error'] = str(exc) or type(exc).__name__
        print('CF-120: ' + evidence['error'], file=sys.stderr, flush=True)
    finally:
        if child is not None and child.poll() is None:
            mesh.stop_process(child)
        if client is not None:
            client.close()
        evidence['cleanup'] = mesh.stop_all() if mesh is not None else {'complete': True, 'errors': []}
        if relay is not None:
            try:
                relay.close()
            except Exception as exc:
                evidence['cleanup']['complete'] = False
                evidence['cleanup'].setdefault('errors', []).append(str(exc))
        try:
            temporary.cleanup()
        except OSError as exc:
            evidence['cleanup']['complete'] = False
            evidence['cleanup'].setdefault('errors', []).append(str(exc))
        if source_files_digest(ROOT) != evidence['source'].get('files_sha256'):
            # Evidence must describe one candidate; an edit during the run invalidates it.
            evidence['error'] = '; '.join(filter(None, [evidence.get('error'), 'source changed during the run']))
        result = conclude(evidence, session, exit_code, manifest)
        evidence['selection']['developer_filter'] = args.select
        save_json(directory / 'contract.json', evidence)
        save_json(output, evidence)
    print(f'CF-120: conformant={evidence["contract_conformant"]}; '
          f'{len(evidence["results"])} cases; evidence: {output}', flush=True)
    if (directory / 'pytest.log').exists():
        print('\n'.join((directory / 'pytest.log').read_text(encoding='utf-8').splitlines()[-25:]), flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
