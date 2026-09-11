"""ARC-060 command-line interface (SRS-FR-098, SRS 22).

Configuration resolves flag > environment variable > gauntlet.yaml > default. Every command accepts
--json. Exit codes (SRS 22.3): 0 success / gate passed, 1 usage or configuration error, 2 genuine
metric breach or failed diagnostic, 3 ungatable run, 4 infrastructure error, 5 calibration bound
exceeded. Codes 2 and 4 are distinct so a pipeline can tell a regression from an outage.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, help="GAUNTLET — the infrastructure crash-test rig for real-time voice AI.")
target_app = typer.Typer(help="Manage targets.")
app.add_typer(target_app, name="target")
console = Console(stderr=True)

EXIT_OK, EXIT_USAGE, EXIT_BREACH, EXIT_UNGATABLE, EXIT_INFRA, EXIT_CALIBRATION = 0, 1, 2, 3, 4, 5
TERMINAL = {"completed", "aborted", "aborted_budget", "failed"}


class Cfg:
    def __init__(self, config_path: str | None, api_url: str | None, debug: bool = False):
        path = Path(config_path or "gauntlet.yaml")
        self.file: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.api_url = (api_url or os.environ.get("GAUNTLET_API_URL") or self.file.get("api_url") or "http://127.0.0.1:8000").rstrip("/")
        self.key = os.environ.get("GAUNTLET_API_KEY", "")
        self.debug = debug

    def get(self, name: str, flag: Any = None, default: Any = None) -> Any:
        if flag is not None:
            return flag
        env = os.environ.get(f"GAUNTLET_{name.upper()}")
        if env is not None:
            return env
        return self.file.get(name, default)


def fail(code: int, message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


def client(cfg: Cfg) -> httpx.Client:
    if not cfg.key:
        fail(EXIT_USAGE, "missing GAUNTLET_API_KEY — create a key in the dashboard under CI gate, then export it")
    return httpx.Client(base_url=cfg.api_url, headers={"Authorization": f"Bearer {cfg.key}"}, timeout=30)


def call(c: httpx.Client, method: str, path: str, **kw: Any) -> httpx.Response:
    """Three attempts with exponential backoff on network failure, then an infrastructure error (exit 4)."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = c.request(method, path, **kw)
            if r.status_code >= 500:
                raise httpx.HTTPStatusError("server error", request=r.request, response=r)
            return r
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            time.sleep(0.5 * (2**attempt))
    fail(EXIT_INFRA, f"infrastructure error, not a regression: {type(last).__name__}: {last}")
    raise AssertionError


def body_or_fail(r: httpx.Response) -> dict[str, Any]:
    if r.status_code >= 400:
        err = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("error", {})
        code = err.get("code", str(r.status_code))
        if code == "ungatable_run":
            fail(EXIT_UNGATABLE, f"ungatable run: {err.get('message')}")
        fail(EXIT_USAGE, f"{code}: {err.get('message', r.text[:200])}")
    return r.json()


def out(data: Any, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")


def resolve_suite(c: httpx.Client, name: str | None) -> str:
    suites = body_or_fail(call(c, "GET", "/v1/suites"))
    if not suites:
        fail(EXIT_USAGE, "no suites in this workspace")
    if name:
        for s in suites:
            if name in (s["id"], s["key"], s["name"]):
                return s["id"]
        fail(EXIT_USAGE, f"suite '{name}' not found")
    return suites[0]["id"]


@app.command()
def init(target_id: str = typer.Option(..., "--target-id"), suite: str = "booking-core", api_url: str | None = None,
         force: bool = False) -> None:
    """Write gauntlet.yaml (contains no secrets)."""
    p = Path("gauntlet.yaml")
    if p.exists() and not force:
        fail(EXIT_USAGE, "gauntlet.yaml exists; pass --force to overwrite")
    doc = {"api_url": api_url or "http://127.0.0.1:8000", "target_id": target_id, "suite": suite, "conditions": "mobile",
           "thresholds": "default", "concurrency": 6, "repeats": 1, "spend_cap_usd": 1.5,
           "gate": {"tolerance_points": 3}}
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    console.print(f"wrote {p}")


@target_app.command("list")
def target_list(as_json: bool = typer.Option(False, "--json"), config: str | None = None, api_url: str | None = None) -> None:
    cfg = Cfg(config, api_url)
    with client(cfg) as c:
        rows = body_or_fail(call(c, "GET", "/v1/targets"))
    if as_json:
        return out(rows, True)
    t = Table("id", "name", "adapter", "verified", "baseline")
    for r in rows:
        t.add_row(r["id"], r["name"], r["adapter"], "yes" if r["verified_at"] else "no", r["baseline_run_id"] or "—")
    Console().print(t)


@app.command()
def run(target: str | None = None, suite: str | None = None, conditions: str | None = None, thresholds: str | None = None,
        concurrency: int | None = None, repeats: int | None = None, spend_cap: float | None = None, seed: int | None = None,
        label: str | None = None, wait: bool = False, timeout: int = 1800, config: str | None = None,
        api_url: str | None = None, as_json: bool = typer.Option(False, "--json")) -> None:
    """Create a run; with --wait, follow it to completion and print the grade."""
    cfg = Cfg(config, api_url)
    with client(cfg) as c:
        rid = _create_run(c, cfg, target, suite, conditions, thresholds, concurrency, repeats, spend_cap, seed, label)
        result = _wait(c, rid, timeout, quiet=as_json) if wait else {"run": {"id": rid}}
    out(result, as_json)
    if not as_json:
        console.print(f"run {rid}")


def _create_run(c: httpx.Client, cfg: Cfg, target: str | None, suite: str | None, conditions: str | None,
                thresholds: str | None, concurrency: int | None, repeats: int | None, spend_cap: float | None,
                seed: int | None, label: str | None) -> str:
    tid = cfg.get("target_id", target)
    if not tid:
        fail(EXIT_USAGE, "no target: pass --target or set target_id in gauntlet.yaml")
    body = {"target_id": tid, "suite_id": resolve_suite(c, cfg.get("suite", suite)),
            "condition_profile_key": cfg.get("conditions", conditions, "clean"),
            "threshold_profile_key": cfg.get("thresholds", thresholds, "default"),
            "concurrency": int(cfg.get("concurrency", concurrency, 5)), "repeats": int(cfg.get("repeats", repeats, 1)),
            "spend_cap_usd": float(cfg.get("spend_cap_usd", spend_cap, 2.0))}
    s = cfg.get("seed", seed)
    if s is not None:
        body["seed"] = int(s)
    if label or os.environ.get("GITHUB_SHA"):
        body["label"] = label or f"ci {os.environ.get('GITHUB_SHA', '')[:8]}"
    for k in ("scenario_keys", "persona_keys"):
        if cfg.file.get(k):
            body[k] = cfg.file[k]
    r = body_or_fail(call(c, "POST", "/v1/runs", json=body, headers={"Idempotency-Key": str(uuid.uuid4())}))
    return r["run"]["id"]


def _wait(c: httpx.Client, rid: str, timeout: int, quiet: bool = False) -> dict[str, Any]:
    start = time.time()
    while True:
        s = body_or_fail(call(c, "GET", f"/v1/runs/{rid}"))
        run_ = s["run"]
        if not quiet:
            done = sum(1 for x in s["calls"] if x["status"] in ("completed", "failed", "needs_review", "errored"))
            console.print(f"  {run_['status']:<10} {done}/{run_['total_calls']} calls", highlight=False)
        if run_["status"] in TERMINAL:
            if not quiet:
                console.print(f"grade {run_['grade'] or '—'}  score {run_['overall'] if run_['overall'] is not None else '—'}"
                              f"  {(s.get('score') or {}).get('suppressed_reason') or ''}")
            return s
        if time.time() - start > timeout:
            fail(EXIT_INFRA, f"run {rid} did not finish within {timeout} s")
        time.sleep(5)


@app.command()
def status(run_id: str, config: str | None = None, api_url: str | None = None,
           as_json: bool = typer.Option(False, "--json")) -> None:
    cfg = Cfg(config, api_url)
    with client(cfg) as c:
        s = body_or_fail(call(c, "GET", f"/v1/runs/{run_id}"))
    out(s, as_json)
    if not as_json:
        console.print(f"{s['run']['status']} grade={s['run']['grade']} score={s['run']['overall']}")


@app.command()
def gate(run_id: str, baseline: str | None = None, tolerance: float | None = None, markdown: str | None = None,
         config: str | None = None, api_url: str | None = None, as_json: bool = typer.Option(False, "--json")) -> None:
    """Evaluate a run against the target's baseline. Exit 2 on a genuine breach."""
    cfg = Cfg(config, api_url)
    tol = cfg.get("tolerance", tolerance, (cfg.file.get("gate") or {}).get("tolerance_points"))
    with client(cfg) as c:
        body: dict[str, Any] = {"run_id": run_id}
        base = baseline or (cfg.file.get("gate") or {}).get("baseline_run_id")
        if base:
            body["baseline_run_id"] = base
        if tol is not None:
            body["tolerance"] = float(tol)
        g = body_or_fail(call(c, "POST", "/v1/gate", json=body))
    _emit_gate(g, markdown, as_json)


def _emit_gate(g: dict[str, Any], markdown: str | None, as_json: bool) -> None:
    if markdown:
        Path(markdown).write_text(g["markdown"], encoding="utf-8")
    out(g, as_json)
    if not as_json:
        sys.stdout.write(g["markdown"])
    raise typer.Exit(EXIT_OK if g["verdict"] == "passed" else EXIT_BREACH)


@app.command()
def report(run_id: str, format: str = typer.Option("md", "--format"), out_path: str | None = typer.Option(None, "--out"),
           share: bool = False, config: str | None = None, api_url: str | None = None) -> None:
    cfg = Cfg(config, api_url)
    with client(cfg) as c:
        if share:
            console.print("share links require a signed-in user; create one from the dashboard")
            raise typer.Exit(EXIT_USAGE)
        path = f"/v1/runs/{run_id}/report.md" if format == "md" else f"/v1/runs/{run_id}/report.json"
        r = call(c, "GET", path)
        if r.status_code >= 400:
            body_or_fail(r)
    text = r.text
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


@app.command()
def ci(config: str | None = None, api_url: str | None = None, comment_out: str = "gauntlet-comment.md",
       verdict_out: str = "gauntlet-verdict.json", timeout: int = 1800) -> None:
    """Run, wait, gate and write the Markdown comment — the one command a pipeline needs."""
    cfg = Cfg(config, api_url)
    with client(cfg) as c:
        rid = _create_run(c, cfg, None, None, None, None, None, None, None, None, None)
        console.print(f"run {rid} created; waiting")
        s = _wait(c, rid, timeout)
        if s["run"]["status"] != "completed":
            Path(comment_out).write_text(f"<!-- gauntlet-gate -->\n## ⚠️ GAUNTLET: run ended `{s['run']['status']}` — "
                                         f"ungatable, not a regression\n", encoding="utf-8")
            fail(EXIT_UNGATABLE, f"run ended {s['run']['status']}; ungatable")
        body: dict[str, Any] = {"run_id": rid}
        g_cfg = cfg.file.get("gate") or {}
        if g_cfg.get("tolerance_points") is not None:
            body["tolerance"] = float(g_cfg["tolerance_points"])
        if g_cfg.get("baseline_run_id"):
            body["baseline_run_id"] = g_cfg["baseline_run_id"]
        r = call(c, "POST", "/v1/gate", json=body)
        if r.status_code == 409:
            err = r.json().get("error", {})
            Path(comment_out).write_text(f"<!-- gauntlet-gate -->\n## ⚠️ GAUNTLET: {err.get('code')}\n\n{err.get('message')}\n",
                                         encoding="utf-8")
            fail(EXIT_UNGATABLE, f"{err.get('code')}: {err.get('message')}")
        g = body_or_fail(r)
    Path(verdict_out).write_text(json.dumps(g, indent=2), encoding="utf-8")
    _emit_gate(g, comment_out, False)


@app.command()
def calibrate(delays: str = "200,500,1000,2000", repetitions: int = 20, out_path: str | None = typer.Option(None, "--out")) -> None:
    """Run the loopback calibration sweep (exit 5 if the bound exceeds the acceptable maximum)."""
    import subprocess

    root = Path(__file__).resolve().parents[3]
    args = [sys.executable, str(root / "calibration" / "run_calibration.py"), "--delays", delays,
            "--repetitions", str(repetitions)]
    if out_path:
        args += ["--out", out_path]
    raise typer.Exit(subprocess.call(args))


if __name__ == "__main__":
    app()
