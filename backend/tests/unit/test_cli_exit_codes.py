"""The CLI's exit codes (SRS 33, PRD 12.7): a pipeline has to tell a regression from an outage.

    0 pass · 1 usage · 2 genuine metric breach · 3 ungatable run · 4 infrastructure · 5 calibration

These were only ever checked by hand. Here the API is a mock transport, so each code is produced by the
path that really produces it: the gate verdict, an error envelope, three failed attempts, a missing key.
"""

import json

import httpx
import pytest
import typer
from typer.testing import CliRunner

from gauntlet.cli import main as cli

runner = CliRunner()

GATE_PASSED = {"verdict": "passed", "breaches": [], "markdown": "<!-- gauntlet-gate -->\n## GAUNTLET gate passed\n"}
GATE_FAILED = {
    "verdict": "failed",
    "breaches": [{"kind": "new_threshold_breach", "metric": "response_latency_p95", "baseline": 786.35,
                  "candidate": 1639.5, "delta": 853.15}],
    "markdown": "<!-- gauntlet-gate -->\n## GAUNTLET gate FAILED\n| `response_latency_p95` | 786.35 | 1,639.5 |\n",
}


def envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "correlation_id": "test"}}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GAUNTLET_API_KEY", "gnt_test")
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)  # the retry backoff, without the wait


def stub_api(monkeypatch, handler) -> None:
    """Every CLI request is answered here; nothing leaves the process."""
    def fake_client(cfg):
        if not cfg.key:
            cli.fail(cli.EXIT_USAGE, "missing GAUNTLET_API_KEY")
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api.test")

    monkeypatch.setattr(cli, "client", fake_client)


def test_a_passing_gate_exits_zero(monkeypatch):
    stub_api(monkeypatch, lambda request: httpx.Response(200, json=GATE_PASSED))
    result = runner.invoke(cli.app, ["gate", "run-1"])
    assert result.exit_code == cli.EXIT_OK
    assert "gate passed" in result.stdout


def test_a_breach_exits_two_and_writes_the_comment(monkeypatch, tmp_path):
    stub_api(monkeypatch, lambda request: httpx.Response(200, json=GATE_FAILED))
    md = tmp_path / "comment.md"
    result = runner.invoke(cli.app, ["gate", "run-1", "--markdown", str(md)])
    assert result.exit_code == cli.EXIT_BREACH  # 2: a regression, not an outage
    assert "response_latency_p95" in md.read_text(encoding="utf-8")


def test_an_ungatable_run_exits_three(monkeypatch):
    stub_api(monkeypatch, lambda request: httpx.Response(
        409, json=envelope("ungatable_run", "candidate run is not gatable (status=aborted)")))
    result = runner.invoke(cli.app, ["gate", "run-1"])
    assert result.exit_code == cli.EXIT_UNGATABLE  # 3: the run never produced a judgement


def test_a_server_that_keeps_failing_exits_four(monkeypatch):
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        return httpx.Response(503, json={"error": {"code": "unavailable", "message": "down"}})

    stub_api(monkeypatch, handler)
    result = runner.invoke(cli.app, ["gate", "run-1"])
    assert result.exit_code == cli.EXIT_INFRA  # 4: infrastructure, so CI must not read it as a regression
    assert len(attempts) == 3  # tried three times before saying so


def test_any_other_api_error_exits_one(monkeypatch):
    stub_api(monkeypatch, lambda request: httpx.Response(404, json=envelope("not_found", "no such run")))
    assert runner.invoke(cli.app, ["gate", "missing"]).exit_code == cli.EXIT_USAGE


def test_a_missing_api_key_exits_one(monkeypatch):
    monkeypatch.delenv("GAUNTLET_API_KEY", raising=False)
    result = runner.invoke(cli.app, ["gate", "run-1"])
    assert result.exit_code == cli.EXIT_USAGE  # 1: the operator has to fix this, not the code


def test_calibration_passes_its_own_exit_code_through(monkeypatch):
    """`gauntlet calibrate` shells out to the sweep, which exits 5 when the rig's own error is too large."""
    import subprocess

    monkeypatch.setattr(subprocess, "call", lambda args: cli.EXIT_CALIBRATION)
    assert runner.invoke(cli.app, ["calibrate"]).exit_code == cli.EXIT_CALIBRATION  # 5: the rig failed its own check
    monkeypatch.setattr(subprocess, "call", lambda args: 0)
    assert runner.invoke(cli.app, ["calibrate"]).exit_code == cli.EXIT_OK


def test_the_json_output_is_the_gate_result(monkeypatch):
    stub_api(monkeypatch, lambda request: httpx.Response(200, json=GATE_FAILED))
    result = runner.invoke(cli.app, ["gate", "run-1", "--json"])
    assert result.exit_code == cli.EXIT_BREACH
    assert json.loads(result.stdout)["breaches"][0]["metric"] == "response_latency_p95"


def test_every_exit_code_is_distinct():
    codes = [cli.EXIT_OK, cli.EXIT_USAGE, cli.EXIT_BREACH, cli.EXIT_UNGATABLE, cli.EXIT_INFRA, cli.EXIT_CALIBRATION]
    assert codes == [0, 1, 2, 3, 4, 5] and len(set(codes)) == len(codes)
    assert issubclass(typer.Exit, Exception)
