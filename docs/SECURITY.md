# Security

Right-sized for a dialler with real abuse potential (PRD 22).

| Threat | Control |
|---|---|
| Dialling someone else's system | Ownership verification before any dial: WebSocket targets echo a fresh nonce; LiveKit targets join with the owner's secret. Any connection change revokes verification. No telephone dialling exists. |
| SSRF via target URLs | Resolve before connecting; reject loopback, private, link-local, multicast, reserved and cloud-metadata ranges; `wss` only outside development; re-resolve at connect time (DNS rebinding). `common/urlguard.py`. |
| Secret exposure | Connection blobs AES-256-GCM encrypted at rest, decrypted only in the worker, never in any response model; masked hints only. API keys: Argon2id hash + 8-char prefix, plaintext shown once. `.env*` git-ignored; `.env.example` holds names only. |
| Leaked CI key | Scopes `run:create`, `run:read`, `gate:execute`; keys can never create keys, targets or thresholds, so a leaked key cannot redefine "passing". Revocation is effective on the next request. |
| Cross-tenant access | One workspace-scoped data layer; other workspaces' rows return 404, never 403. |
| Abuse / cost | Per-workspace concurrent-run and daily spend ceilings; per-run spend ceiling checked before billable calls; unpriced providers charged a default; rate limits on every write path and on public reports. |
| Prompt injection from agent speech | Transcript passed to the evaluator as delimited data; the evaluator has no tools; citations are validated by substring; two passes surface disagreement as needs-review. |
| Malicious scenarios | YAML safe loader, JSON Schema validation, no templating or evaluation. |
| Share-link enumeration | 32 bytes of entropy, rate-limited, revoked or expired links return 404; public view exposes no workspace identifiers. |
| Logs | JSON logs with a field allowlist; no secrets, audio or transcripts. |

Guest mode (`ALLOW_GUEST=true`) is a shared, rate-limited demo workspace for hackathon judging; it is
off by default and should be off in any real deployment.
