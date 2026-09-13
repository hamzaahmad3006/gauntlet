"""TC-121 / SRS-SEC-001: structured logs carry allowlisted identifiers only — never secrets or transcripts."""

import json
import logging

from gauntlet.common.logging import JsonFormatter


def test_tc121_formatter_drops_everything_not_allowlisted():
    rec = logging.LogRecord("gauntlet.test", logging.INFO, __file__, 1, "call finished", None, None)
    rec.run_id = "run-1"
    rec.api_key = "gnt_supersecretvalue1234"
    rec.authorization = "Bearer eyJhbGciOi"
    rec.transcript = "my card number is 4111"
    rec.token = "tok"
    out = JsonFormatter().format(rec)
    data = json.loads(out)
    assert data["run_id"] == "run-1" and data["msg"] == "call finished"
    for leaked in ("gnt_supersecretvalue1234", "eyJhbGciOi", "4111", "tok\""):
        assert leaked not in out
