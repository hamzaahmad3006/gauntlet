"""Threshold profiles (SRS-FR-090). A profile is a versioned document mapping each scored metric to
ideal / threshold / limit / direction, plus sub-score weights, hard-breach limits and the comparison
band. Nothing that decides a verdict is a hidden constant in code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class Bound:
    ideal: float
    threshold: float
    limit: float
    direction: str  # lower_is_better | higher_is_better

    def validate(self, metric: str, profile: str) -> None:
        if self.direction == "lower_is_better":
            ok = self.ideal < self.threshold < self.limit
        elif self.direction == "higher_is_better":
            ok = self.ideal > self.threshold > self.limit
        else:
            raise ProfileError(f"profile '{profile}': metric '{metric}' has unknown direction '{self.direction}'")
        if not ok:
            order = "ideal < threshold < limit" if self.direction == "lower_is_better" else "ideal > threshold > limit"
            raise ProfileError(f"profile '{profile}': metric '{metric}' violates {order}")


@dataclass(frozen=True)
class SubScoreDef:
    id: str
    name: str
    weight: float
    inputs: dict[str, float]  # metric -> intra weight


@dataclass(frozen=True)
class ThresholdProfile:
    key: str
    bounds: dict[str, Bound]
    subscores: tuple[SubScoreDef, ...]
    hard_breaches: dict[str, float]
    comparison_band_points: float = 3.0
    gate_tolerance_points: float = 3.0
    source: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def version_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.source).encode()).hexdigest()

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> ThresholdProfile:
        key = str(doc.get("key") or "")
        if not key:
            raise ProfileError("threshold profile has no key")
        bounds: dict[str, Bound] = {}
        for metric, spec in (doc.get("metrics") or {}).items():
            b = Bound(float(spec["ideal"]), float(spec["threshold"]), float(spec["limit"]), str(spec["direction"]))
            b.validate(metric, key)
            bounds[metric] = b
        subs = []
        for sid, spec in (doc.get("subscores") or {}).items():
            inputs = {m: float(w) for m, w in (spec.get("inputs") or {}).items()}
            for m in inputs:
                if m not in bounds:
                    raise ProfileError(f"profile '{key}': sub-score {sid} uses metric '{m}' with no bounds")
            if abs(sum(inputs.values()) - 1.0) > 1e-9:
                raise ProfileError(f"profile '{key}': intra-weights of {sid} must sum to 1")
            subs.append(SubScoreDef(sid, str(spec.get("name", sid)), float(spec["weight"]), inputs))
        if abs(sum(s.weight for s in subs) - 1.0) > 1e-9:
            raise ProfileError(f"profile '{key}': sub-score weights must sum to 1")
        hb = {k: float(v) for k, v in (doc.get("hard_breaches") or {}).items()}
        return cls(
            key=key,
            bounds=bounds,
            subscores=tuple(subs),
            hard_breaches=hb,
            comparison_band_points=float(doc.get("comparison_band_points", 3.0)),
            gate_tolerance_points=float((doc.get("gate") or {}).get("tolerance_points", 3.0)),
            source=doc,
        )


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
