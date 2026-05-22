"""
rate_limiter.py — Rate Limiting (Phase 11)

API throttling and abuse prevention using SlowAPI.
Limits applied via FastAPI dependencies.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Use a default in-memory storage for simplicity, but in production,
# we should ideally pass a Redis URL to the Limiter.
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
# To keep dependencies light and work without redis-py if not fully configured for slowapi,
# we stick to default memory limiter. If we strictly needed redis, we'd use slowapi.storage.redis.

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

def setup_rate_limiting(app):
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
