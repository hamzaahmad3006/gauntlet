"""Run the API under the precise real-time event loop (gauntlet.common.rt), so in-process calls pace
audio correctly on Windows too.

    python -m gauntlet.serve [--host 0.0.0.0] [--port 8000]
"""

from __future__ import annotations

import argparse
import os

import uvicorn

from gauntlet.common import rt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = ap.parse_args()
    config = uvicorn.Config("gauntlet.server:app", host=args.host, port=args.port, proxy_headers=True,
                            forwarded_allow_ips="*", ws_ping_interval=20, log_config=None)
    server = uvicorn.Server(config)
    rt.run(server.serve())


if __name__ == "__main__":
    main()
