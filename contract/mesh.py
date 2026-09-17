"""Seven real APIs plus the synthetic provider, owned by the parent runner."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ('vault', 'reader', 'generator', 'verifier', 'publisher', 'librarian', 'analyst')


class PortBindError(RuntimeError):
    """A reserved port was claimed before the owned service could bind it."""


def bind_conflict(message):
    text = str(message).lower()
    return any(marker in text for marker in (
        'address already in use', 'errno 10048', 'winerror 10048', 'errno 98', 'errno 48',
    ))


def addresses_for(names):
    held, addresses = [], {}
    try:
        for name in names:
            connection = socket.socket()
            connection.bind(('127.0.0.1', 0))
            held.append(connection)
            addresses[name] = 'http://127.0.0.1:' + str(connection.getsockname()[1])
    finally:
        for connection in held:
            connection.close()
    return addresses


def listening(url):
    port = int(url.rsplit(':', 1)[1])
    with socket.socket() as connection:
        connection.settimeout(.2)
        return connection.connect_ex(('127.0.0.1', port)) == 0


class Mesh:
    def __init__(self, directory, env, addresses):
        # The caller has prepared env before this import (run_mesh imports service URLs).
        from scripts.run_mesh import APPS, stop_process
        self.apps = {**APPS, 'provider': ('contract.provider_stub:app', False)}
        self.stop_process = stop_process
        self.directory, self.env, self.addresses = Path(directory), env, addresses
        self.log_dir = self.directory / 'logs'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.processes, self.streams, self.history = {}, {}, []
        self.owned = []  # every process ever started, including replaced ones
        self.bind_conflicts, self.log_offsets = set(), {}
        self.bound_services = set()
        self.relay_url = None
        self.health = {}

    def start(self, name, overrides=None):
        if self.running(name):
            raise RuntimeError(name + ' is already running; use restart')
        reference, factory = self.apps[name]
        env = dict(self.env)
        if name in ('generator', 'verifier'):
            env.update(OPENAI_API_KEY='cf120-synthetic-provider-key',
                       OPENAI_BASE_URL=self.addresses['provider'] + '/v1')
        if self.relay_url:
            env['VAULT_URL'] = self.relay_url + '/vault'
            env['VERIFIER_URL'] = self.relay_url + '/verifier'
        env.update(overrides or {})
        stream = (self.log_dir / (name + '.log')).open('a', encoding='utf-8')
        self.streams[name] = stream
        self.log_offsets[name] = stream.tell()
        self.bind_conflicts.discard(name)
        self.bound_services.discard(name)
        command = [sys.executable, '-B', '-m', 'uvicorn', reference, '--host', '127.0.0.1',
                   '--port', self.addresses[name].rsplit(':', 1)[1], '--log-config',
                   str(ROOT / 'scripts' / 'http_logging.json')]
        if factory:
            command.append('--factory')
        try:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except BaseException:
            stream.close()
            raise
        self.processes[name] = process
        self.owned.append((name, process))
        self.history.append({'service': name, 'pid': process.pid, 'command': command})

    def running(self, name):
        return name in self.processes and self.processes[name].poll() is None

    def tail(self, name):
        path = self.log_dir / (name + '.log')
        if not path.exists():
            return ''
        with path.open(encoding='utf-8', errors='replace') as stream:
            stream.seek(self.log_offsets.get(name, 0))
            return '\n'.join(stream.read().splitlines()[-35:])

    def failed_bind(self, name):
        process = self.processes.get(name)
        if process is not None and process.poll() is not None and bind_conflict(self.tail(name)):
            self.bind_conflicts.add(name)
        return name in self.bind_conflicts

    def ready(self, names, timeout=120):
        pending = set(names)
        deadline = time.monotonic() + timeout
        with requests.Session() as session:
            session.trust_env = False
            while pending and time.monotonic() < deadline:
                for name in list(pending):
                    if not self.running(name):
                        error = PortBindError if self.failed_bind(name) else RuntimeError
                        raise error(name + ' exited during startup:\n' + self.tail(name))
                    if name not in self.bound_services:
                        # A foreign API can answer /health while our process is
                        # still importing and has not yet lost the bind race.
                        # Uvicorn emits this line only after its socket binds;
                        # tail() is restricted to this exact process launch.
                        marker = 'Uvicorn running on ' + self.addresses[name] + ' '
                        if marker not in self.tail(name):
                            continue
                        self.bound_services.add(name)
                    try:
                        response = session.get(self.addresses[name] + '/health', timeout=.5, allow_redirects=False)
                        body = response.json() if response.status_code == 200 else None
                        if self.running(name) and isinstance(body, dict) and body.get('status') == 'ok':
                            self.health[name] = body
                            pending.remove(name)
                    except (requests.RequestException, ValueError):
                        pass
                if pending:
                    time.sleep(.1)
        if pending:
            raise RuntimeError('Readiness deadline: ' + ', '.join(pending) + '\n' +
                               '\n'.join(self.tail(name) for name in pending))

    def start_all(self):
        for name in self.apps:
            self.start(name)
        self.ready(self.apps)

    def stop(self, name):
        process = self.processes.get(name)
        try:
            if process is not None:
                foreign_listener = self.failed_bind(name)
                self.stop_process(process)
                if process.poll() is None:
                    raise RuntimeError(name + ' process did not stop')
                # A failed bind never owned this listener. Keep it alive and
                # let the startup runner reserve a completely new port map.
                if not foreign_listener:
                    deadline = time.monotonic() + 5
                    while listening(self.addresses[name]) and time.monotonic() < deadline:
                        time.sleep(.05)
                    if listening(self.addresses[name]):
                        raise RuntimeError(name + ' listener remained after owned process exit')
        finally:
            stream = self.streams.pop(name, None)
            if stream:
                stream.close()

    def restart(self, name, overrides=None):
        self.stop(name)
        for attempt in range(3):
            try:
                self.start(name, overrides)
                self.ready([name], timeout=60)
                return
            except Exception:
                self.stop(name)
                if attempt == 2:
                    raise

    def stop_all(self):
        errors = []
        for name in reversed(list(self.processes)):
            try:
                self.stop(name)
            except Exception as exc:
                errors.append(str(exc))
        for name, process in self.owned:
            if process.poll() is None:
                try:
                    self.stop_process(process)
                except Exception as exc:
                    errors.append(f'{name} pid {process.pid}: {exc}')
                if process.poll() is None:
                    errors.append(f'{name} pid {process.pid} survived cleanup')
        return {'complete': not errors, 'errors': errors,
                'owned': [{'service': name, 'pid': process.pid, 'exit_code': process.poll()}
                          for name, process in self.owned],
                'processes': [{'service': name, 'pid': process.pid, 'exit_code': process.poll(),
                               'listener_owned': name not in self.bind_conflicts,
                               'listener_closed': not listening(self.addresses[name])}
                              for name, process in self.processes.items()]}
