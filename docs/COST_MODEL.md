# Cost model

Two numbers, never summed, never in one column.

## Rig cost — MEASURED

GAUNTLET's own spend, from counters the providers returned, times operator-entered prices in
`config/pricing.yaml` (each entry carries `source` and `retrieved_at`; older than 90 days warns):

```
rig_cost = Σ caller-LLM and scorer tokens / 1000 × price
         + Σ synthesised characters (cache misses only) / 1000 × price
         + Σ referee audio seconds, converted to the price unit
         + Σ LiveKit participant minutes × price
```

Every term comes from a stored counter, so recomputation is exact. The shipped file holds **zero
placeholders on purpose**: a run against zero prices reports $0 with a `pricing_not_configured` flag
rather than a plausible-looking number. A provider with no price entry is charged `unknown_unit_cost_usd`
so it cannot bypass the spend ceiling, which is checked before every billable call.

## Target cost — ESTIMATED

Only when the target owner declares unit prices (`unit_prices` on the target). Token counts inside the
target are not observable, so they are modelled:

```
est_agent_tokens_out = ceil(agent_transcript_chars / 4)
est_agent_tokens_in  = ceil((caller_text_chars + agent_transcript_chars) / 4) × context_factor   # 1.5
est_target_cost = tokens_in/1000 × llm.prompt_price_per_1k_tokens
                + tokens_out/1000 × llm.completion_price_per_1k_tokens
                + agent_transcript_chars/1000 × tts.price_per_1k_characters
                + caller_audio_seconds/60 × stt.price_per_minute
```

Undeclared components are listed by name. Cost per successful session is undefined — shown as such, not
zero — when there are no successful sessions.

## Pre-run estimate

`POST /v1/runs/estimate` multiplies expected turns per call (from each scenario's turn budget) by
per-turn usage of the configured providers, assumes no cache hits (an upper bound), and prints every
assumption. It has no side effects.
