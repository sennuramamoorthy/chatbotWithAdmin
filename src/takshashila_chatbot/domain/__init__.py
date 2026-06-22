"""Deterministic domain logic.

Everything here is pure (no I/O) and dependency-injected (notably a ``Clock``),
so it is exhaustively unit-testable and carries the system's hard correctness
guarantees: date-sensitive status, lead validation, rate limiting, input guards,
and the first-pass boundary policy.
"""
