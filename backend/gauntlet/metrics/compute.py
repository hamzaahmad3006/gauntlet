"""ARC-023 metric computer — per-turn and per-call metrics from event timelines (SRS-FR-061..066).

Pure functions over integer-nanosecond intervals on the one shared clock. Missing inputs yield
``None``, never zero (SRS: "missing events produce explicitly null metrics").
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

Interval = tuple[int, int]

YIELD_TIMEOUT_MS = 2000
DEAD_AIR_THRESHOLD_MS = 1500


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Union of intervals, sorted, with overlaps and touching spans merged (no double counting)."""
    out: list[Interval] = []
    for s, e in sorted((s, e) for s, e in intervals if e > s):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def total_ns(intervals: Iterable[Interval]) -> int:
    return sum(e - s for s, e in merge(intervals))


def intersection_ns(a: Iterable[Interval], b: Iterable[Interval]) -> int:
    """Total overlap between two interval sets — talk-over when a = caller, b = agent (SRS-FR-063)."""
    ma, mb = merge(a), merge(b)
    i = j = 0
    acc = 0
    while i < len(ma) and j < len(mb):
        s = max(ma[i][0], mb[j][0])
        e = min(ma[i][1], mb[j][1])
        if e > s:
            acc += e - s
        if ma[i][1] < mb[j][1]:
            i += 1
        else:
            j += 1
    return acc


def speaking_at(intervals: Sequence[Interval], t: int) -> Interval | None:
    for s, e in intervals:
        if s <= t < e:
            return (s, e)
    return None


@dataclass
class AgentWindow:
    """The span in which the conversation is waiting on, or listening to, the agent: from the caller's
    last voiced sample to the caller's next utterance (or call end)."""

    start_ns: int
    end_ns: int


def dead_air(windows: Sequence[AgentWindow], caller: Sequence[Interval], agent: Sequence[Interval],
             threshold_ms: float = DEAD_AIR_THRESHOLD_MS) -> int:
    """Total duration of agent-side silences exceeding the threshold (SRS-FR-064, narrowed).

    Within each agent window, silence = time when neither party speaks. Gaps between the caller's
    last word and the agent's first audio, and pauses inside the agent's response, count. The caller's
    own think time (after the agent finished, before the caller speaks again) is outside every window,
    so rig latency can never be reported as the target's dead air.
    """
    threshold_ns = int(threshold_ms * 1_000_000)
    busy = merge(list(caller) + list(agent))
    acc = 0
    for w in windows:
        cursor = w.start_ns
        last_agent_end = None
        for s, e in busy:
            if e <= w.start_ns:
                continue
            if s >= w.end_ns:
                break
            s_c, e_c = max(s, w.start_ns), min(e, w.end_ns)
            if s_c - cursor > threshold_ns:
                acc += s_c - cursor
            cursor = max(cursor, e_c)
            last_agent_end = e_c
        # trailing silence inside the window counts only if the agent never answered at all
        if last_agent_end is None and w.end_ns - cursor > threshold_ns:
            acc += w.end_ns - cursor
    return acc


@dataclass
class Interruption:
    turn_idx: int
    scheduled_offset_ms: float
    onset_ns: int | None = None  # first voiced sample of the interruption as transmitted
    status: str = "pending"  # applied | not_applicable | not_reached
    barge_stop_ms: float | None = None
    no_yield: bool = False


def classify_interruption(intr: Interruption, agent: Sequence[Interval],
                          yield_timeout_ms: float = YIELD_TIMEOUT_MS) -> Interruption:
    """Barge-in stop time (SRS-FR-062). Censored at the yield timeout with no_yield=True; an
    interruption fired while the agent was silent is not_applicable and excluded from everything."""
    if intr.onset_ns is None:
        intr.status = "not_reached"
        return intr
    seg = speaking_at(agent, intr.onset_ns)
    if seg is None:
        intr.status = "not_applicable"
        intr.barge_stop_ms = None
        return intr
    intr.status = "applied"
    stop_ms = (seg[1] - intr.onset_ns) / 1_000_000
    if stop_ms > yield_timeout_ms:
        intr.barge_stop_ms = float(yield_timeout_ms)
        intr.no_yield = True
    else:
        intr.barge_stop_ms = round(stop_ms, 3)
        intr.no_yield = False
    return intr


@dataclass
class TurnRecord:
    idx: int
    caller_text: str | None = None
    agent_text: str | None = None
    agent_confidence: float | None = None
    t_caller_first_voiced_ns: int | None = None
    t_caller_last_sample_ns: int | None = None  # post-chaos, actual transmit timeline
    t_caller_last_nominal_ns: int | None = None  # pre-chaos
    t_agent_first_audio_ns: int | None = None
    t_agent_last_audio_ns: int | None = None
    latency_ms: float | None = None  # attributed: excludes injected delay/jitter by construction
    raw_latency_ms: float | None = None  # from pre-chaos end; includes injected delay
    censored: bool = False
    premature: bool = False
    rig_overhead_ms: float | None = None
    inference_ms: float | None = None
    synthesis_ms: float | None = None
    cache_hit: bool | None = None
    fallback_used: bool = False
    barge_stop_ms: float | None = None
    no_yield: bool = False
    interruption_status: str | None = None
    epoch: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tts_chars: int = 0
    usage_estimated: bool = False
    extra: dict = field(default_factory=dict)


def latency(turn: TurnRecord) -> None:
    """Fill latency fields from timestamps (SRS-FR-061)."""
    if turn.censored or turn.t_agent_first_audio_ns is None or turn.t_caller_last_sample_ns is None:
        turn.latency_ms = None
        turn.raw_latency_ms = None
        return
    if turn.t_agent_first_audio_ns < turn.t_caller_last_sample_ns:
        turn.premature = True
        turn.latency_ms = None
        turn.raw_latency_ms = None
        return
    turn.latency_ms = round((turn.t_agent_first_audio_ns - turn.t_caller_last_sample_ns) / 1e6, 3)
    if turn.t_caller_last_nominal_ns is not None:
        turn.raw_latency_ms = round((turn.t_agent_first_audio_ns - turn.t_caller_last_nominal_ns) / 1e6, 3)


@dataclass
class CallMetrics:
    duration_ms: float | None
    talkover_ms: float | None
    dead_air_ratio: float | None  # percent
    dead_air_ms: float | None
    first_speech_ns: int | None
    last_speech_ns: int | None


def call_metrics(caller: Sequence[Interval], agent: Sequence[Interval], windows: Sequence[AgentWindow],
                 threshold_ms: float = DEAD_AIR_THRESHOLD_MS) -> CallMetrics:
    busy = merge(list(caller) + list(agent))
    if not busy:
        return CallMetrics(None, None, None, None, None, None)
    first, last = busy[0][0], busy[-1][1]
    duration = last - first
    talk = intersection_ns(caller, agent)
    dead = dead_air(windows, caller, agent, threshold_ms)
    ratio = round(100.0 * dead / duration, 3) if duration > 0 else None
    return CallMetrics(
        duration_ms=round(duration / 1e6, 3),
        talkover_ms=round(talk / 1e6, 3),
        dead_air_ratio=ratio,
        dead_air_ms=round(dead / 1e6, 3),
        first_speech_ns=first,
        last_speech_ns=last,
    )
