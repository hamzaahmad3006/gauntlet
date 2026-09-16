"""Publish GAUNTLET to a Hugging Face Space (Docker SDK).

    python infra/huggingface/deploy.py --token hf_xxx --space hamza/gauntlet

The Space gets the repository as it stands at HEAD, with `infra/huggingface/Dockerfile` as its root
Dockerfile and a README carrying the Space metadata. Provider keys are never sent: add them afterwards in
the Space's Settings → Variables and secrets.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]

README = """---
title: GAUNTLET
emoji: 📞
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# GAUNTLET — the crash-test rig for real-time voice AI

Synthetic callers dial a voice agent over real audio, every turn is measured from the caller's ear under
seeded network chaos, and the result becomes a deterministic readiness score that can fail a pull request.

- **Talk to agent** — call the bundled restaurant agent from your browser and hear how fast it answers.
- **Runs → New run** — watch an AI caller do the same while the latency is measured.
- **Compare / CI gate / Calibration** — a graded A against a graded C, the gate that failed on four
  breaches, and the rig's own 3.897 ms measurement error.

Source: https://github.com/hamzaahmad3006/gauntlet

This Space runs on free hardware with no persistent disk: it sleeps when idle, runs at most two calls at a
time, and forgets its runs when it restarts. Numbers produced here are not comparable with the committed
benchmarks.
"""


def run(cmd: list[str], cwd: pathlib.Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="Hugging Face write token")
    ap.add_argument("--space", required=True, help="owner/space, e.g. hamza/gauntlet")
    args = ap.parse_args()
    owner, _, name = args.space.partition("/")
    if not owner or not name:
        print("--space must look like owner/space", file=sys.stderr)
        return 2

    from huggingface_hub import HfApi

    api = HfApi(token=args.token)
    api.create_repo(repo_id=args.space, repo_type="space", space_sdk="docker", exist_ok=True)
    print(f"space ready: https://huggingface.co/spaces/{args.space}")

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "space"
        work.mkdir()
        # the repository exactly as committed, so nothing ignored or untracked is published
        archive = pathlib.Path(tmp) / "head.tar"
        run(["git", "archive", "-o", str(archive), "HEAD"], ROOT)
        shutil.unpack_archive(str(archive), str(work))
        shutil.copy(ROOT / "infra" / "huggingface" / "Dockerfile", work / "Dockerfile")
        (work / "README.md").write_text(README, encoding="utf-8")
        run(["git", "init", "-q", "-b", "main"], work)
        run(["git", "add", "-A"], work)
        run(["git", "-c", "user.name=hamzaahmad3006", "-c", "user.email=hamzaahmad3006@gmail.com",
             "commit", "-qm", "Publish GAUNTLET"], work)
        url = f"https://user:{args.token}@huggingface.co/spaces/{args.space}"
        run(["git", "push", "--force", url, "main"], work)

    host = f"{owner}-{name}".lower().replace(".", "-")
    print(f"pushed. the Space builds now: https://{host}.hf.space")
    print("add GROQ_API_KEY, ELEVENLABS_API_KEY, SPEECHMATICS_API_KEY and SECRET_ENCRYPTION_KEY")
    print("in Settings → Variables and secrets, then restart the Space.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
