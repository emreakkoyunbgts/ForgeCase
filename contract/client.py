"""Raw HTTP assertions and controls for an explicitly owned CF-120 mesh."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import requests


_request_traces = ContextVar('cf120_request_traces', default=None)


@contextmanager
def capture_request_traces():
    """Collect only service names and trace IDs for one pytest execution phase."""
    entries = []
    token = _request_traces.set(entries)
    try:
        yield entries
    finally:
        _request_traces.reset(token)


def record_trace(service, trace):
    entries = _request_traces.get()
    if (entries is not None and isinstance(trace, str) and 0 < len(trace) <= 4096
            and all(32 <= ord(char) < 127 for char in trace)):
        entry = {'service': service, 'trace_id': trace}
        if entry not in entries:
            entries.append(entry)


class Client:
    def __init__(self, config):
        self.config = config
        self.addresses = config['addresses']
        self.relay_url = config['relay_url']
        self.artifact_dir = Path(config['artifact_dir'])
        self.session = requests.Session()
        self.session.trust_env = False

    def request(self, service, method, path, expected=200, trace=None, headers=None, **kwargs):
        selected = requests.structures.CaseInsensitiveDict({
            'Authorization': 'Bearer ' + self.config['token'],
            'X-Correlation-ID': trace or str(uuid4()),
        })
        selected.update(headers or {})
        selected = requests.structures.CaseInsensitiveDict(
            {key: value for key, value in selected.items() if value is not None})
        # Register before I/O so timeouts and disconnected dependencies retain
        # their correlation ID without retaining the request or its headers.
        record_trace(service, selected.get('X-Correlation-ID'))
        kwargs.setdefault('timeout', 100)
        response = self.session.request(method, self.addresses[service] + path,
                                        headers=selected, allow_redirects=False, **kwargs)
        record_trace(service, response.headers.get('X-Correlation-ID'))
        if expected is not None:
            assert response.status_code == expected, (service, path, expected,
                                                       response.status_code, response.text[:3000])
        supplied_trace = selected.get('X-Correlation-ID')
        if supplied_trace and len(supplied_trace) <= 4096 and all(32 <= ord(c) < 127 for c in supplied_trace):
            assert response.headers.get('X-Correlation-ID') == supplied_trace
        return response

    def control(self, path, **body):
        response = self.session.post(self.relay_url + path, json=body,
            headers={'X-CF120-Control': self.config['control_token']}, timeout=100)
        assert response.status_code == 200, response.text
        return response.json()

    def boundary_calls(self, trace=None):
        response = self.session.get(self.relay_url + '/__calls',
            headers={'X-CF120-Control': self.config['control_token']}, timeout=5)
        response.raise_for_status()
        calls = response.json()['calls']
        selected = [call for call in calls if trace is None or call['trace'] == trace]
        # Workflow uses the shipped HTTP client rather than Client.request.
        # A case's explicit boundary lookup still links its observed trace.
        if trace is not None:
            for call in selected:
                record_trace(call['target'], call['trace'])
        return selected

    def provider_state(self):
        response = self.session.get(self.addresses['provider'] + '/__calls', timeout=5)
        response.raise_for_status()
        return response.json()

    def provider_calls(self, trace=None):
        return [call for call in self.provider_state()['calls']
                if trace is None or call['correlation_id'] == trace]

    def arm_provider(self, fault, stage='any', trace=None):
        response = self.session.post(self.addresses['provider'] + '/__control',
            json={'fault': fault, 'stage': stage, 'correlation_id': trace}, timeout=5)
        assert response.status_code == 200, response.text
        return response.json()

    def fault(self, target, trace, **kwargs):
        return self.control('/__fault', target=target, trace=trace, **kwargs)

    def restart(self, service, env=None):
        return self.control('/__restart', service=service, env=env)

    @contextmanager
    def down(self, service):
        if service == 'provider':
            # A restarted provider starts with an empty call log; keep the evidence.
            state = self.provider_state()
            assert state['armed_unused'] == [], state['armed_unused']
            target = Path(self.config['run_directory']) / f'provider-calls-before-restart-{uuid4().hex}.json'
            target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        self.control('/__stop', service=service)
        try:
            yield
        finally:
            self.restart(service)

    def artifact_snapshot(self):
        return {path.relative_to(self.artifact_dir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.artifact_dir.rglob('*') if path.is_file()}

    def delete_source(self, record_id):
        response = self.request('vault', 'GET', '/engagements/' + record_id, expected=None)
        if response.status_code == 404:
            return
        assert response.status_code == 200
        self.request('vault', 'DELETE', '/engagements/' + record_id, expected=204,
                     headers={'If-Match': response.headers['ETag']})

    def close(self):
        self.session.close()
