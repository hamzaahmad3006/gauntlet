"""Every router in the API. server.py mounts this list and nothing else."""

from gauntlet.routes import calls, compare, fixtures, gate, keys, reports, runs, suites, system, targets

routers = [system.router, keys.router, targets.router, suites.router, runs.router, calls.router, compare.router,
           gate.router, reports.router, fixtures.router]
