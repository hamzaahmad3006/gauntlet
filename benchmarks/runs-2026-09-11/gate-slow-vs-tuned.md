<!-- gauntlet-gate -->
## ❌ GAUNTLET gate FAILED

| | Baseline | Candidate | Δ |
|---|---|---|---|
| Readiness | 100 (A) | 76.17 (C) | -23.83 |

### Breaches

| Metric | Kind | Baseline | Candidate | Δ |
|---|---|---|---|---|
| `readiness` | score_drop | 100 | 76.17 | -23.83 |
| `response_latency_p95` | new_threshold_breach | 786.35 | 1,639.5 | 853.15 |
| `time_to_first_response_p50` | new_threshold_breach | 752.31 | 1,601.31 | 849 |
| `dead_air_ratio` | new_threshold_breach | 0 | 15.59 | 15.59 |

Baseline run `01a0915a-cebd-72ce-afc2-62a9449ee25c` · candidate run `01a0915a-cf16-7634-bb94-c696bc6c9f74`
[Full report](http://localhost:5173/dashboard/runs/01a0915a-cf16-7634-bb94-c696bc6c9f74)
