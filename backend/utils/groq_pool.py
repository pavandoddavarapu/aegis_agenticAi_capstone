"""
groq_pool.py — Groq API Key Pool with Automatic Rotation

Reads up to 7 Groq API keys from environment variables:
  GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3, ... GROQ_API_KEY_7

On 429 (rate limit) or connection errors, automatically rotates to the
next available key and retries the request transparently.

Usage (replaces all manual _get_client() calls in agents):
    from backend.utils.groq_pool import get_groq_client, groq_chat_with_retry
    
    # Simple: get a pre-rotated client
    client = get_groq_client()
    
    # Better: use groq_chat_with_retry() — handles rotation automatically
    response = groq_chat_with_retry(
        model="llama-3.3-70b-versatile",
        messages=[...],
        max_tokens=800,
        temperature=0.2,
    )
"""
from __future__ import annotations

import os
import time
import threading
from typing import List, Optional, Any, Dict
from openai import OpenAI
from backend.utils.logger import logger


# ── Key Discovery ─────────────────────────────────────────────────────────────

def _load_groq_keys() -> List[str]:
    """
    Load all configured Groq API keys from environment variables.
    Reads GROQ_API_KEY, GROQ_API_KEY_2 ... GROQ_API_KEY_7.
    """
    keys: List[str] = []
    
    # Primary key
    primary = os.getenv("GROQ_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    
    # Additional keys 2-7
    for i in range(2, 8):
        key = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if key:
            keys.append(key)
    
    if not keys:
        logger.warning("[GroqPool] No GROQ_API_KEY found in environment.")
    else:
        logger.info(f"[GroqPool] Loaded {len(keys)} Groq API key(s).")
    
    return keys


# ── Key Pool Singleton ────────────────────────────────────────────────────────

class GroqKeyPool:
    """
    Thread-safe round-robin API key pool with per-key cooldown tracking.
    
    When a key hits a 429 or connection error, it is temporarily put on
    cooldown and the next key is used automatically.
    """
    
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    COOLDOWN_SECONDS = 60     # how long a rate-limited key waits before retry
    MAX_KEY_RETRIES  = 3      # max attempts across all keys before giving up
    
    def __init__(self):
        self._keys: List[str] = _load_groq_keys()
        self._cooldowns: Dict[str, float] = {}   # key → cooldown_until timestamp
        self._lock = threading.Lock()
        self._index = 0   # round-robin cursor
        self._clients: Dict[str, OpenAI] = {}    # key → OpenAI client singleton
    
    def _is_on_cooldown(self, key: str) -> bool:
        cooldown_until = self._cooldowns.get(key, 0.0)
        return time.time() < cooldown_until
    
    def _put_on_cooldown(self, key: str, duration: float = COOLDOWN_SECONDS):
        self._cooldowns[key] = time.time() + duration
        logger.warning(
            f"[GroqPool] Key ...{key[-8:]} put on cooldown for {duration:.0f}s "
            f"(until {time.strftime('%H:%M:%S', time.localtime(self._cooldowns[key]))})"
        )
    
    def _get_client_for_key(self, key: str) -> OpenAI:
        """Get or create a cached OpenAI client for a given API key."""
        if key not in self._clients:
            self._clients[key] = OpenAI(
                api_key=key,
                base_url=self.GROQ_BASE_URL,
            )
        return self._clients[key]
    
    def get_available_client(self) -> Optional[tuple[OpenAI, str]]:
        """
        Returns (client, key) for the next available (non-rate-limited) key.
        Returns None if all keys are on cooldown.
        """
        with self._lock:
            if not self._keys:
                return None
            
            # Try each key starting from current index
            for attempt in range(len(self._keys)):
                idx = (self._index + attempt) % len(self._keys)
                key = self._keys[idx]
                
                if not self._is_on_cooldown(key):
                    self._index = (idx + 1) % len(self._keys)
                    return self._get_client_for_key(key), key
            
            # All keys on cooldown — find the one that expires soonest
            soonest_key = min(self._keys, key=lambda k: self._cooldowns.get(k, 0))
            soonest_wait = self._cooldowns.get(soonest_key, 0) - time.time()
            logger.warning(
                f"[GroqPool] All {len(self._keys)} keys are on cooldown. "
                f"Soonest available in {soonest_wait:.1f}s. Using it anyway..."
            )
            return self._get_client_for_key(soonest_key), soonest_key
    
    def mark_key_rate_limited(self, key: str, retry_after: float = 60.0):
        """Mark a key as rate-limited with the given cooldown duration."""
        with self._lock:
            self._put_on_cooldown(key, duration=max(retry_after, self.COOLDOWN_SECONDS))
    
    def mark_key_connection_error(self, key: str):
        """Mark a key as having a connection error (shorter cooldown)."""
        with self._lock:
            self._put_on_cooldown(key, duration=10.0)
    
    def chat_with_retry(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 800,
        temperature: float = 0.2,
        response_format: Optional[Dict] = None,
        **kwargs: Any,
    ):
        """
        Execute a Groq chat completion with automatic key rotation on errors.
        
        Tries each available key in round-robin order. On 429 or connection
        errors, marks the current key and switches to the next.
        
        Args:
            model:           Groq model name (e.g. "llama-3.3-70b-versatile")
            messages:        Chat messages list
            max_tokens:      Max tokens to generate
            temperature:     Sampling temperature
            response_format: Optional response format dict (e.g. {"type": "json_object"})
        
        Returns:
            OpenAI ChatCompletion response object.
        
        Raises:
            RuntimeError: If all keys fail after MAX_KEY_RETRIES attempts.
        """
        last_exc = None
        
        for attempt in range(max(self.MAX_KEY_RETRIES, len(self._keys))):
            result = self.get_available_client()
            if result is None:
                raise RuntimeError("[GroqPool] No Groq API keys configured.")
            
            client, key = result
            key_suffix = f"...{key[-8:]}"
            
            try:
                kwargs_build = dict(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if response_format:
                    kwargs_build["response_format"] = response_format
                kwargs_build.update(kwargs)
                
                logger.debug(f"[GroqPool] Attempt {attempt + 1} with key {key_suffix}")
                response = client.chat.completions.create(**kwargs_build)
                
                if attempt > 0:
                    logger.info(f"[GroqPool] Succeeded with key {key_suffix} on attempt {attempt + 1}")
                return response
            
            except Exception as exc:
                last_exc = exc
                exc_str = str(exc)
                
                # Parse retry-after from 429 error message if present
                retry_after = 60.0
                if "429" in exc_str or "rate_limit_exceeded" in exc_str or "Rate limit" in exc_str:
                    # Try to parse "Please try again in Xs"
                    import re
                    m = re.search(r"try again in\s+([\d.]+)([smh])", exc_str)
                    if m:
                        val = float(m.group(1))
                        unit = m.group(2)
                        if unit == "m":
                            val *= 60
                        elif unit == "h":
                            val *= 3600
                        retry_after = min(val + 5, 300)  # cap at 5 min
                    
                    logger.warning(
                        f"[GroqPool] Key {key_suffix} hit rate limit "
                        f"(retry_after={retry_after:.0f}s). Rotating key..."
                    )
                    self.mark_key_rate_limited(key, retry_after=retry_after)
                
                elif "Connection error" in exc_str or "connection" in exc_str.lower():
                    logger.warning(
                        f"[GroqPool] Key {key_suffix} connection error. "
                        f"Rotating key... Error: {exc_str[:100]}"
                    )
                    self.mark_key_connection_error(key)
                
                else:
                    # Non-transient error — don't rotate, just raise
                    logger.error(f"[GroqPool] Non-transient error with key {key_suffix}: {exc_str[:200]}")
                    raise
        
        raise RuntimeError(
            f"[GroqPool] All key rotation attempts exhausted. Last error: {last_exc}"
        )
    
    def has_keys(self) -> bool:
        return bool(self._keys)


# ── Module-level singleton ────────────────────────────────────────────────────
_pool: GroqKeyPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> GroqKeyPool:
    """Get or create the global GroqKeyPool singleton."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = GroqKeyPool()
    return _pool


def get_groq_client() -> OpenAI:
    """
    Get a Groq OpenAI-compatible client (uses next available key).
    For simple cases — prefer groq_chat_with_retry() for full rotation.
    """
    pool = get_pool()
    result = pool.get_available_client()
    if result is None:
        # Fallback to OpenAI if no Groq keys
        openai_key = os.getenv("OPENAI_API_KEY")
        return OpenAI(api_key=openai_key)
    client, _ = result
    return client


def groq_chat_with_retry(
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 800,
    temperature: float = 0.2,
    response_format: Optional[Dict] = None,
    **kwargs: Any,
):
    """
    Module-level convenience wrapper for groq_pool.chat_with_retry().
    Automatically rotates keys on 429/connection errors.
    """
    pool = get_pool()
    
    if not pool.has_keys():
        # Fallback to OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(api_key=openai_key)
        kw = dict(model="gpt-4o-mini", messages=messages, max_tokens=max_tokens, temperature=temperature)
        if response_format:
            kw["response_format"] = response_format
        return client.chat.completions.create(**kw)
    
    return pool.chat_with_retry(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
        **kwargs,
    )
