# Adapters

Nothing above the adapter layer knows which transport is in use. An adapter only has to deliver 20 ms,
16 kHz mono int16 frames in each direction (`backend/gauntlet/caller/adapters/base.py`).

## WebSocket PCM — `gauntlet.pcm.v1`

The deliberately minimal protocol: any agent can be tested with about thirty lines of server code.

1. Client connects (`wss://` only; `ws://127.0.0.1` in development), optional `Authorization: Bearer`.
2. Client sends a JSON text frame:
   ```json
   {"type": "hello", "protocol": "gauntlet.pcm.v1", "sample_rate": 16000, "frame_ms": 20, "nonce": "<hex>"}
   ```
3. Server replies with a JSON hello that **echoes the nonce** (this is ownership verification):
   ```json
   {"type": "hello", "protocol": "gauntlet.pcm.v1", "nonce": "<same hex>"}
   ```
4. Both sides stream **binary frames of 640 bytes** — 320 samples of 16 kHz mono signed 16-bit
   little-endian PCM, one frame per 20 ms. The server should pace in real time; a server that bursts
   audio is timed as heard (playout clock, D-16).
5. Either side may send `{"type": "bye", "reason": "..."}`; the socket closes with code 1000.

More than 10 malformed binary frames terminate the call with `protocol_error`. Unknown text frames are
ignored. Fixtures may send `{"type": "marker", ...}` messages; real agents never need to.

Minimal server (Python, `websockets`):

```python
async def handler(ws):
    hello = json.loads(await ws.recv())
    await ws.send(json.dumps({"type": "hello", "protocol": "gauntlet.pcm.v1", "nonce": hello["nonce"]}))
    async for msg in ws:
        if isinstance(msg, bytes):
            for frame in my_agent.process(msg):   # your VAD + STT + LLM + TTS
                await ws.send(frame)              # 640-byte frames, paced at 20 ms
```

## LiveKit room (WebRTC)

Connection: `{"url": "wss://<project>.livekit.cloud", "api_key": "...", "api_secret": "...",
"room": "gauntlet-{call_id}"}`. The worker mints a participant token, joins as
`gauntlet-caller-<call_id>`, publishes one mono audio track and subscribes to the first remote audio
track. No remote audio within 20 s → `no_remote_audio`. Verification = a successful token mint and join,
which requires the owner's API secret. Requires `pip install "backend[livekit]"`.

## Bundled synthetic agent

`/fixtures/agent` on every deployment speaks the protocol above. Query parameters make it a programmable
agent: `mode=agent|calibration|echo`, `endpoint_ms`, `delay_ms`, `yield_ms` (`never` = does not yield
to barge-in), `greeting=1`. The two bundled targets are two tunings of it. It is a test fixture, not a
product.
