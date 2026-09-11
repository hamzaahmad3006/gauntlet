"""Media adapters. Nothing above this layer knows which transport is in use (SRS 47.1)."""

from gauntlet.caller.adapters.base import Transport, TransportError

__all__ = ["Transport", "TransportError"]
