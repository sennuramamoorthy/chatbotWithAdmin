"""HTTP transport layer (FastAPI).

Thin adapters over the application services: request parsing, SSE streaming,
rate limiting, and soft-fail. No business logic lives here.
"""
