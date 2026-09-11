"""Piecewise-linear normalisation to 0–100 (SRS 19.2, PRD 12.3).

ideal -> 100, threshold -> 70, limit -> 0. Arithmetic is decimal with 6 significant digits, then
rounded half-up to two decimals, so ordering effects of binary floating point cannot change a score.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context, Decimal

from gauntlet.scoring.profile import Bound

CTX = Context(prec=6, rounding=ROUND_HALF_UP)
TWO = Decimal("0.01")


def D(x: float | int | str | Decimal) -> Decimal:
    return CTX.create_decimal(str(x)) if not isinstance(x, Decimal) else CTX.plus(x)


def q2(x: Decimal) -> Decimal:
    return x.quantize(TWO, rounding=ROUND_HALF_UP)


def normalise(value: float, bound: Bound) -> Decimal:
    v, ideal, thr, lim = D(value), D(bound.ideal), D(bound.threshold), D(bound.limit)
    h, t, s = D(100), D(30), D(70)
    if bound.direction == "lower_is_better":
        if v <= ideal:
            out = h
        elif v <= thr:
            out = CTX.subtract(h, CTX.divide(CTX.multiply(t, CTX.subtract(v, ideal)), CTX.subtract(thr, ideal)))
        elif v < lim:
            out = CTX.subtract(s, CTX.divide(CTX.multiply(s, CTX.subtract(v, thr)), CTX.subtract(lim, thr)))
        else:
            out = D(0)
    else:
        if v >= ideal:
            out = h
        elif v >= thr:
            out = CTX.subtract(h, CTX.divide(CTX.multiply(t, CTX.subtract(ideal, v)), CTX.subtract(ideal, thr)))
        elif v > lim:
            out = CTX.subtract(s, CTX.divide(CTX.multiply(s, CTX.subtract(thr, v)), CTX.subtract(thr, lim)))
        else:
            out = D(0)
    return q2(out)


def passes(value: float, bound: Bound) -> bool:
    return value <= bound.threshold if bound.direction == "lower_is_better" else value >= bound.threshold
