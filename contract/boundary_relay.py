"""Loopback-only recording relay and owned-mesh controls for CF-120.

Normal requests reach the real Vault/Verifier. Faults are one-shot, selected by
trace, target and HTTP method. Recorded credentials are equality flags only.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
from urllib.parse import urlsplit

import requests


class Relay:
    def __init__(self, mesh, port, token):
        self.mesh, self.token = mesh, token
        self.calls, self.faults = [], []
        self.lock = threading.Lock()
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, content, headers=None):
                if not isinstance(content, bytes):
                    content = json.dumps(content, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                supplied = headers or {'Content-Type': 'application/json'}
                for key, value in supplied.items():
                    if key.lower() not in {'transfer-encoding', 'content-length', 'content-encoding',
                                           'connection', 'server', 'date'}:
                        self.send_header(key, value)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                try:
                    self.wfile.write(content)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # A deliberately timed-out consumer already disconnected.

            def handle_request(self):
                length = int(self.headers.get('Content-Length', '0'))
                body = self.rfile.read(length) if length else b''
                if self.path.startswith('/__'):
                    if self.headers.get('X-CF120-Control') != relay.token:
                        return self.reply(403, {'detail': 'control token required'})
                    try:
                        data = json.loads(body) if body else {}
                        if self.path == '/__calls':
                            with relay.lock:
                                value = {'calls': list(relay.calls), 'armed_unused': [
                                    dict(f) for f in relay.faults if not f['used']]}
                        elif self.path == '/__fault' and self.command == 'POST':
                            if data.get('target') not in {'vault', 'verifier'} or not data.get('trace'):
                                return self.reply(422, {'detail': 'target and trace required'})
                            with relay.lock:
                                relay.faults.append({**data, 'used': False})
                            value = {'armed': True}
                        elif self.path == '/__clear' and self.command == 'POST':
                            with relay.lock:
                                unused = [dict(f) for f in relay.faults if not f['used']]
                                if not unused:
                                    relay.faults.clear()
                            # Erasing an armed-but-unobserved fault would hide
                            # a test that never reached the boundary it claims.
                            if unused:
                                return self.reply(409, {'detail': 'armed faults were never used',
                                                        'armed_unused': unused})
                            value = {'cleared': True}
                        elif self.path in {'/__stop', '/__restart'} and self.command == 'POST':
                            name = data['service']
                            if name not in relay.mesh.processes:
                                return self.reply(422, {'detail': 'unknown service'})
                            if self.path == '/__stop':
                                relay.mesh.stop(name)
                            else:
                                relay.mesh.restart(name, data.get('env'))
                            value = {'service': name, 'running': relay.mesh.running(name)}
                        else:
                            return self.reply(404, {'detail': 'unknown control route'})
                        return self.reply(200, value)
                    except Exception as exc:
                        return self.reply(500, {'detail': str(exc)})
                parts = self.path.split('/', 2)
                target = parts[1] if len(parts) > 1 else ''
                if target not in {'vault', 'verifier'}:
                    return self.reply(404, {'detail': 'unknown boundary'})
                path = '/' + (parts[2] if len(parts) > 2 else '')
                trace = self.headers.get('X-Correlation-ID')
                try:
                    payload = json.loads(body) if body else None
                except ValueError:
                    payload = None
                entry = {'target': target, 'method': self.command, 'path': path,
                         'trace': trace, 'authorization_matches': self.headers.get('Authorization') ==
                         'Bearer ' + relay.mesh.env['CASEFORGE_TOKEN'],
                         'idempotency_key': self.headers.get('Idempotency-Key'),
                         'payload': payload, 'started_at': time.time()}
                with relay.lock:
                    fault = next((f for f in relay.faults if not f['used']
                                  and f['target'] == target and f['trace'] == trace
                                  and f.get('method', self.command) == self.command), None)
                    if fault:
                        fault['used'] = True
                    relay.calls.append(entry)
                if fault:
                    entry['injected'] = True
                    # Interruptible: close() must not wait out a long timeout fault.
                    relay.closing.wait(min(float(fault.get('delay', 0)), 90))
                    status = int(fault.get('status', 200))
                    entry.update(status=status, finished_at=time.time())
                    content = fault.get('body', {})
                    if isinstance(content, str):
                        content = content.encode('utf-8')
                    return self.reply(status, content, fault.get('headers'))
                headers = {key: value for key, value in self.headers.items()
                           if key.lower() not in {'host', 'connection', 'content-length'}}
                try:
                    with requests.Session() as session:
                        session.trust_env = False
                        response = session.request(self.command, relay.mesh.addresses[target] + path,
                                                   headers=headers, data=body or None,
                                                   timeout=85, allow_redirects=False)
                    entry.update(status=response.status_code, finished_at=time.time())
                    self.reply(response.status_code, response.content, dict(response.headers))
                except requests.RequestException:
                    # A stopped dependency must reach the consumer as a transport
                    # failure, not as an HTTP status the relay invented: close
                    # the connection without a response.
                    entry.update(status='transport_error', finished_at=time.time())
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = handle_request

        self.closing = threading.Event()
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        # Non-daemon handlers are joined by server_close(): cleanup is not
        # claimed while a relayed request is still writing its evidence.
        self.server.daemon_threads = False
        self.server.block_on_close = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def start(self):
        self.thread.start()

    def close(self):
        self.closing.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('Boundary control server did not stop')
