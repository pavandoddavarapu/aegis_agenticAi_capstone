"""
retries.py — API Hardening Utilities (Phase 11)

Decorators for retry handling, timeouts, and graceful fallbacks 
for external network requests. Uses the tenacity library.
"""
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx
from backend.utils.logger import logger

def log_retry_attempt(retry_state):
    logger.warning(f"[Retry] Attempt {retry_state.attempt_number} failed. Retrying...")

# Standard retry decorator for external HTTP calls (PubMed, OpenAI, etc.)
# Stops after 3 attempts. Waits 1s, then 2s, then 4s.
with_retries = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, TimeoutError)),
    after=log_retry_attempt,
    reraise=True
)

def graceful_fallback(fallback_value):
    """Decorator to return a fallback value if all retries fail."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"[Fallback] All retries failed for {func.__name__}: {e}. Returning fallback.")
                return fallback_value
        return wrapper
    return decorator
