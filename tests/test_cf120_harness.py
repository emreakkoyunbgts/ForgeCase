"""Acceptance evidence and owned-resource failures must never look like a pass."""
from copy import deepcopy
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from contract.boundary_relay import Relay
from contract.evidence import conclude, source_files_digest
from contract.mesh import Mesh, PortBindError, listening


CASE_IDS = ["contract/test_example.py::test_first", "contract/test_example.py::test_second"]


def successful_run():
    evidence = {
        "source": {"working_tree_dirty": False, "files_sha256": "unchanged"},
        "provider": {"type": "synthetic-http", "real_model": False},
        "preflight_complete": True, "cleanup": {"complete": True, "errors": []},
        "release_eligible": False,
    }
    session = {
        "collected": list(CASE_IDS), "session_finished": True, "errors": [],
        "results": [{"nodeid": case, "outcome": "passed", "duration": .1,
                     "phases": {"setup": "passed", "call": "passed", "teardown": "passed"}}
                    for case in CASE_IDS],
    }
    manifest = {"cases": {case: {"owner": "test owner"} for case in CASE_IDS}}
    return evidence, session, manifest


@pytest.mark.parametrize("dirty", [False, True])
def test_complete_contract_run_reports_clean_and_dirty_candidates_without_release_approval(dirty):
    evidence, session, manifest = successful_run()
    evidence["source"]["working_tree_dirty"] = dirty
    # Even a stale caller-supplied flag cannot approve synthetic evidence for release.
    evidence["release_eligible"] = True
    assert conclude(evidence, session, 0, manifest) == 0
    assert evidence["execution_complete"] is True
    assert evidence["contract_conformant"] is True
    assert evidence["acceptance_ready"] is (not dirty)
    assert evidence["release_eligible"] is False
    assert evidence["failures"] == []


@pytest.mark.parametrize("scenario", [
    "empty_manifest", "zero_collected", "partial_selection", "unexpected_test",
    "missing_result", "unfinished_session", "collection_error", "nonzero_exit",
    "cleanup_failed", "preflight_failed", "runner_error",
])
def test_incomplete_or_failed_run_cannot_be_accepted(scenario):
    evidence, session, manifest = successful_run()
    exit_code = 0
    if scenario == "empty_manifest":
        manifest["cases"] = {}
        session.update(collected=[], results=[])
    elif scenario == "zero_collected":
        session.update(collected=[], results=[])
    elif scenario == "partial_selection":
        session["collected"].pop()
        session["results"].pop()
    elif scenario == "unexpected_test":
        session["collected"].append("contract/test_unlisted.py::test_extra")
    elif scenario == "missing_result":
        session["results"].pop()
    elif scenario == "unfinished_session":
        session["session_finished"] = False
    elif scenario == "collection_error":
        session["errors"] = [{"phase": "collection", "reason": "ImportError", "owner": "harness"}]
    elif scenario == "nonzero_exit":
        exit_code = 2
    elif scenario == "cleanup_failed":
        evidence["cleanup"] = {"complete": False, "errors": ["owned listener survived"]}
    elif scenario == "preflight_failed":
        evidence["preflight_complete"] = False
    else:
        evidence["error"] = "source changed during the run"

    assert conclude(evidence, session, exit_code, manifest) != 0
    assert evidence["contract_conformant"] is False
    assert evidence["acceptance_ready"] is False
    assert evidence["release_eligible"] is False
    if scenario in {"zero_collected", "partial_selection"}:
        assert evidence["selection"]["missing_case_ids"]
    if scenario == "unexpected_test":
        assert evidence["selection"]["unexpected_case_ids"]


@pytest.mark.parametrize(("phase", "outcome", "wasxfail", "expected"), [
    ("setup", "failed", False, "failed"),
    ("call", "failed", False, "failed"),
    ("teardown", "failed", False, "failed"),
    ("setup", "skipped", False, "skipped"),
    ("call", "skipped", True, "xfailed"),
    ("call", "passed", True, "xpassed"),
])
def test_pytest_reporting_preserves_phase_failures_skips_xfail_and_xpass(
    monkeypatch, phase, outcome, wasxfail, expected,
):
    # Exercise the same phase aggregator used by the real subprocess, including
    # a successful teardown following a failure and pytest's non-strict XPASS.
    from contract import conftest as reporting
    evidence, session, manifest = successful_run()
    monkeypatch.setattr(reporting, "STATE", session)
    monkeypatch.setattr(reporting, "REPORTS", {})
    monkeypatch.delenv("CF120_SESSION_REPORT", raising=False)
    for case in CASE_IDS:
        for current_phase in ("setup", "call", "teardown"):
            selected = case == CASE_IDS[0] and current_phase == phase
            report = SimpleNamespace(
                nodeid=case, when=current_phase, outcome=outcome if selected else "passed",
                duration=.1, longrepr="intentional harness probe" if selected else "",
                passed=(outcome == "passed") if selected else True,
            )
            if selected and wasxfail:
                report.wasxfail = "known failure is still not contract acceptance"
            reporting.pytest_runtest_logreport(report)
    assert session["results"][0]["outcome"] == expected
    assert session["results"][0]["phase"] == phase
    # Non-strict xfail/skip can leave pytest at exit 0; evidence must reject it.
    assert conclude(evidence, session, 0, manifest) != 0
    assert evidence["failures"][0]["owner"] == "test owner"
    assert evidence["failures"][0]["outcome"] == expected
    assert evidence["contract_conformant"] is False
    assert evidence["release_eligible"] is False


@pytest.fixture
def relay():
    mesh = SimpleNamespace(env={"CASEFORGE_TOKEN": "local-harness-service"}, addresses={}, processes={})
    boundary = Relay(mesh, 0, "local-harness-control")
    boundary.start()
    try:
        yield boundary
    finally:
        boundary.close()
        assert not boundary.thread.is_alive()
        assert not listening(boundary.url)


@pytest.fixture
def http():
    with requests.Session() as session:
        session.trust_env = False
        yield session


def test_clear_cannot_erase_an_armed_unused_fault(relay, http):
    headers = {"X-CF120-Control": relay.token}
    armed = http.post(relay.url + "/__fault", json={
        "target": "vault", "trace": "fault-must-be-observed", "method": "GET", "status": 503,
    }, headers=headers, timeout=3)
    assert armed.status_code == 200
    assert len(http.get(relay.url + "/__calls", headers=headers, timeout=3).json()["armed_unused"]) == 1
    cleared = http.post(relay.url + "/__clear", headers=headers, timeout=3)
    state = http.get(relay.url + "/__calls", headers=headers, timeout=3).json()
    assert 400 <= cleared.status_code < 500, "clear must reject an unused fault instead of erasing its evidence"
    assert len(state["armed_unused"]) == 1
    consumed = http.get(relay.url + "/vault/probe", headers={"X-Correlation-ID": "fault-must-be-observed"}, timeout=3)
    assert consumed.status_code == 503
    assert http.post(relay.url + "/__clear", headers=headers, timeout=3).status_code == 200


def test_relay_close_finishes_or_cancels_active_handlers_before_claiming_cleanup(http):
    mesh = SimpleNamespace(env={"CASEFORGE_TOKEN": "local-harness-service"}, addresses={}, processes={})
    boundary = Relay(mesh, 0, "local-harness-control")
    boundary.start()
    closed = False
    result = {}
    worker = None
    try:
        armed = http.post(boundary.url + "/__fault", json={
            "target": "vault", "trace": "close-drains-work", "method": "GET", "delay": 2,
        }, headers={"X-CF120-Control": boundary.token}, timeout=3)
        assert armed.status_code == 200

        def request_delayed_fault():
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.get(boundary.url + "/vault/probe", timeout=5,
                                           headers={"X-Correlation-ID": "close-drains-work"})
                    result["status"] = response.status_code
            except requests.RequestException as exc:
                result["cancelled"] = type(exc).__name__

        worker = threading.Thread(target=request_delayed_fault)
        worker.start()
        deadline = time.monotonic() + 3
        while not boundary.calls and time.monotonic() < deadline:
            time.sleep(.01)
        assert boundary.calls, "the delayed request did not reach the real relay socket"
        boundary.close()
        closed = True
        worker.join(timeout=.25)
        assert not worker.is_alive(), "close returned while a relay request was still running"
        assert boundary.calls[-1].get("finished_at") is not None, "cleanup left unfinished call evidence"
        assert not boundary.thread.is_alive()
        assert not listening(boundary.url)
        assert result
    finally:
        # Also clean up against the intentionally failing pre-fix implementation.
        if worker is not None:
            worker.join(timeout=6)
        if not closed:
            boundary.close()


def test_real_process_crash_during_startup_is_reported_with_its_log(tmp_path):
    mesh = Mesh(tmp_path, dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), {'broken': 'http://127.0.0.1:9'})
    mesh.apps = {'broken': ('contract.module_that_does_not_exist:app', False)}
    mesh.start('broken')
    try:
        with pytest.raises(RuntimeError, match='broken exited during startup') as caught:
            mesh.ready(['broken'], timeout=60)
        assert 'module_that_does_not_exist' in str(caught.value)
    finally:
        cleanup = mesh.stop_all()
    assert cleanup['complete'] is True
    assert cleanup['owned'][0]['exit_code'] is not None


def test_interrupted_run_still_writes_a_failed_report(tmp_path, monkeypatch):
    from scripts import contract_mesh as runner

    evidence, _, manifest = successful_run()
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "cases.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "initial_evidence", lambda *_: deepcopy(evidence))
    monkeypatch.setattr(runner.os, "environ", dict(os.environ))

    def interrupted(self):
        raise KeyboardInterrupt()

    monkeypatch.setattr(runner.Mesh, "start_all", interrupted)
    output = tmp_path / "interrupted.json"
    assert runner.main(["--output", str(output)]) != 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["error"].startswith("KeyboardInterrupt")
    assert report["execution_complete"] is False and report["contract_conformant"] is False
    assert report["cleanup"]["complete"] is True


def test_runner_boot_failure_closes_started_process_logs_and_real_relay(tmp_path, monkeypatch):
    from scripts import contract_mesh as runner

    evidence, _, manifest = successful_run()
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "cases.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "initial_evidence", lambda *_: deepcopy(evidence))
    # main prepares process environment; isolate that mutation from other tests.
    monkeypatch.setattr(runner.os, "environ", dict(os.environ))
    streams, processes, relays = [], [], []

    class FakeProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return self.returncode

    def start_process(*args, **kwargs):
        streams.append(kwargs["stdout"])
        assert not streams[-1].closed
        if processes:
            raise OSError("intentional second-service boot failure")
        process = FakeProcess()
        processes.append(process)
        return process

    class BootFailureMesh(Mesh):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.stop_process = lambda process: setattr(process, "returncode", 0)

    class ObservedRelay(Relay):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            relays.append(self)

    monkeypatch.setattr(runner, "Mesh", BootFailureMesh)
    monkeypatch.setattr(runner, "Relay", ObservedRelay)
    monkeypatch.setattr("contract.mesh.subprocess.Popen", start_process)
    output = tmp_path / "result.json"
    assert runner.main(["--output", str(output)]) != 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert "intentional second-service boot failure" in report["error"]
    assert report["contract_conformant"] is False
    assert report["cleanup"]["complete"] is True
    assert len(processes) == 1 and processes[0].poll() == 0
    assert len(streams) == 2 and all(stream.closed for stream in streams)
    assert relays and all(not item.thread.is_alive() and not listening(item.url) for item in relays)


@pytest.mark.parametrize("bind_error", [
    "[Errno 10048] error while attempting to bind: Only one usage of each socket address is normally permitted",
    "[WinError 10048] Only one usage of each socket address is normally permitted",
    "[Errno 98] Address already in use",
])
def test_foreign_healthy_api_cannot_satisfy_readiness_and_survives_bind_cleanup(tmp_path, monkeypatch, http, bind_error):
    requests_seen = []

    class ForeignAPI(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests_seen.append(self.path)
            body = b'{"status":"ok","service":"vault"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    foreign = ThreadingHTTPServer(("127.0.0.1", 0), ForeignAPI)
    foreign_thread = threading.Thread(target=foreign.serve_forever)
    foreign_thread.start()
    url = "http://127.0.0.1:" + str(foreign.server_port)
    mesh = Mesh(tmp_path, {}, {"vault": url})
    streams = []

    class ImportingThenFailedProcess:
        pid = 23456
        polls = 0

        def poll(self):
            self.polls += 1
            if self.polls < 3:
                return None  # App imports while an unrelated /health is already green.
            if self.polls == 3:
                streams[0].write(bind_error + "\n")
                streams[0].flush()
            return 1

    def spawn(*args, **kwargs):
        streams.append(kwargs["stdout"])
        return ImportingThenFailedProcess()

    monkeypatch.setattr("contract.mesh.subprocess.Popen", spawn)
    try:
        mesh.start("vault")
        with pytest.raises(PortBindError, match="10048|Address already in use"):
            mesh.ready(["vault"], timeout=3)
        assert requests_seen == [], "the runner contacted a service before its owned process bound the port"
        cleanup = mesh.stop_all()
        assert cleanup["complete"] is True
        assert cleanup["processes"][0]["listener_owned"] is False
        assert cleanup["processes"][0]["listener_closed"] is False
        assert streams[0].closed
        assert http.get(url + "/health", timeout=3).status_code == 200
    finally:
        mesh.stop_all()
        foreign.shutdown()
        foreign.server_close()
        foreign_thread.join(timeout=3)


def test_runner_reallocates_the_whole_map_after_windows_bind_failure(tmp_path, monkeypatch):
    from scripts import contract_mesh as runner
    evidence, _, manifest = successful_run()
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "cases.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "initial_evidence", lambda *_: deepcopy(evidence))
    monkeypatch.setattr(runner.os, "environ", dict(os.environ))
    attempted = []

    class CollisionThenNonretryableFailure(Mesh):
        def start_all(self):
            attempted.append(dict(self.addresses))
            if len(attempted) == 1:
                raise PortBindError("vault exited: [Errno 10048] Only one usage of each socket address")
            raise RuntimeError("second attempt reached; stop the test before launching services")

    monkeypatch.setattr(runner, "Mesh", CollisionThenNonretryableFailure)
    output = tmp_path / "retry.json"
    assert runner.main(["--output", str(output)]) != 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(attempted) == 2
    assert attempted[0] != attempted[1]
    assert [item["retryable_bind_conflict"] for item in report["startup_attempts"]] == [True, False]
    assert all(item["cleanup"]["complete"] for item in report["startup_attempts"])
    assert report["cleanup"]["complete"] is True


def test_failed_process_stop_still_closes_its_log(tmp_path):
    mesh = Mesh(tmp_path, {}, {"vault": "http://127.0.0.1:9"})
    mesh.processes["vault"] = SimpleNamespace(pid=34567, poll=lambda: None)
    stream = (tmp_path / "owned.log").open("w", encoding="utf-8")
    mesh.streams["vault"] = stream

    def cannot_stop(_):
        raise RuntimeError("simulated stop failure")

    mesh.stop_process = cannot_stop
    with pytest.raises(RuntimeError, match="simulated stop failure"):
        mesh.stop("vault")
    assert stream.closed


@pytest.mark.parametrize("config_name", [
    "scripts/http_logging.json", "requirements.txt", "requirements-dev.txt", "requirements.lock",
    "constraints.txt", "pytest.ini", ".env.example", "pyproject.toml", "uv.lock", "poetry.lock",
])
def test_candidate_digest_covers_nonsecret_dependency_and_test_configuration(tmp_path, config_name):
    path = tmp_path / config_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("original config\n", encoding="utf-8")
    before = source_files_digest(tmp_path)
    path.write_text("changed config\n", encoding="utf-8")
    assert source_files_digest(tmp_path) != before


def test_candidate_digest_is_checkout_independent_and_excludes_local_secret_env(tmp_path):
    roots = [tmp_path / "first-checkout", tmp_path / "second-checkout"]
    for root in roots:
        (root / "contract").mkdir(parents=True)
        (root / "contract" / "case.py").write_text("pass\n", encoding="utf-8")
        (root / "requirements.txt").write_text("pytest>=8\n", encoding="utf-8")
    assert source_files_digest(roots[0]) == source_files_digest(roots[1])
    digest = source_files_digest(roots[0])
    (roots[0] / ".env").write_text("OPENAI_API_KEY=never-record-this-placeholder\n", encoding="utf-8")
    assert source_files_digest(roots[0]) == digest
