"""
groq_pool.py — Groq & Gemini API Key Pool with Automatic Rotation

Reads up to 7 Groq API keys and 5 Gemini API keys from environment variables:
  GROQ_API_KEY, GROQ_API_KEY_2...7
  GEMINI_API_KEY, GEMINI_API_KEY_2...5

On 429 (rate limit) or connection errors, automatically rotates to the
next available key for the requested model and retries the request transparently.
"""
from __future__ import annotations

import os
import time
import re
import threading
from typing import List, Optional, Any, Dict
from openai import OpenAI
from backend.utils.logger import logger


# ── Key Discovery ─────────────────────────────────────────────────────────────

def _load_groq_keys() -> List[str]:
    """Load all configured Groq API keys from environment variables."""
    keys: List[str] = []
    primary = os.getenv("GROQ_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    for i in range(2, 8):
        key = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if key:
            keys.append(key)
    if not keys:
        logger.warning("[GroqPool] No GROQ_API_KEY found in environment.")
    else:
        logger.info(f"[GroqPool] Loaded {len(keys)} Groq API key(s).")
    return keys


def _load_gemini_keys() -> List[str]:
    """Load all configured Gemini API keys from environment variables."""
    keys: List[str] = []
    primary = os.getenv("GEMINI_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    for i in range(2, 6):
        key = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
        if key:
            keys.append(key)
    if not keys:
        logger.warning("[GroqPool] No GEMINI_API_KEY found in environment.")
    else:
        logger.info(f"[GroqPool] Loaded {len(keys)} Gemini API key(s).")
    return keys


# ── Key Pool Singleton ────────────────────────────────────────────────────────

class GroqKeyPool:
    """
    Thread-safe round-robin API key pool with per-key cooldown tracking.
    Supports both Groq and Gemini (OpenAI-compatible endpoint) key rotation.
    """
    
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
    COOLDOWN_SECONDS = 60     # how long a rate-limited key waits before retry
    MAX_KEY_RETRIES  = 3      # max attempts across all keys before giving up
    
    def __init__(self):
        self._groq_keys: List[str] = _load_groq_keys()
        self._gemini_keys: List[str] = _load_gemini_keys()
        self._cooldowns: Dict[str, float] = {}   # key → cooldown_until timestamp
        self._lock = threading.Lock()
        self._groq_index = 0   # round-robin cursor for Groq
        self._gemini_index = 0 # round-robin cursor for Gemini
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
    
    def _get_client_for_key(self, key: str, is_gemini: bool = False) -> OpenAI:
        """Get or create a cached OpenAI client for a given API key."""
        if key not in self._clients:
            base_url = self.GEMINI_BASE_URL if is_gemini else self.GROQ_BASE_URL
            self._clients[key] = OpenAI(
                api_key=key,
                base_url=base_url,
            )
        return self._clients[key]
    
    def get_available_client(self, model: str = "") -> Optional[tuple[OpenAI, str]]:
        """
        Returns (client, key) for the next available (non-rate-limited) key.
        Automatically selects Gemini or Groq pool based on model prefix.
        """
        is_gemini = model.startswith("gemini-")
        keys = self._gemini_keys if is_gemini else self._groq_keys
        
        with self._lock:
            if not keys:
                return None
            
            # Select correct index pointer
            index = self._gemini_index if is_gemini else self._groq_index
            
            # Try each key starting from current index
            for attempt in range(len(keys)):
                idx = (index + attempt) % len(keys)
                key = keys[idx]
                
                if not self._is_on_cooldown(key):
                    if is_gemini:
                        self._gemini_index = (idx + 1) % len(keys)
                    else:
                        self._groq_index = (idx + 1) % len(keys)
                    return self._get_client_for_key(key, is_gemini), key
            
            # All keys on cooldown — find the one that expires soonest
            soonest_key = min(keys, key=lambda k: self._cooldowns.get(k, 0))
            soonest_wait = self._cooldowns.get(soonest_key, 0) - time.time()
            logger.warning(
                f"[GroqPool] All {len(keys)} {'Gemini' if is_gemini else 'Groq'} keys are on cooldown. "
                f"Soonest available in {soonest_wait:.1f}s. Using it anyway..."
            )
            return self._get_client_for_key(soonest_key, is_gemini), soonest_key
    
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
        Execute a chat completion with automatic key rotation on errors.
        """
        last_exc = None
        is_gemini = model.startswith("gemini-")
        keys = self._gemini_keys if is_gemini else self._groq_keys
        
        for attempt in range(max(self.MAX_KEY_RETRIES, len(keys))):
            result = self.get_available_client(model)
            if result is None:
                raise RuntimeError(f"[GroqPool] No API keys configured for model: {model}")
            
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
                
                logger.debug(f"[GroqPool] Attempt {attempt + 1} with key {key_suffix} for model {model}")
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
            f"[GroqPool] All key rotation attempts exhausted for model {model}. Last error: {last_exc}"
        )
    
    def has_keys(self, model: str = "") -> bool:
        if model.startswith("gemini-"):
            return bool(self._gemini_keys)
        return bool(self._groq_keys)


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


def get_groq_client(model: str = "") -> OpenAI:
    """
    Get a client (uses next available key from the correct pool).
    """
    pool = get_pool()
    result = pool.get_available_client(model)
    if result is None:
        # Fallback to OpenAI if no keys
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
    Module-level convenience wrapper for key pool chat_with_retry().
    Automatically routes between Groq and Gemini and handles fallback.
    """
    pool = get_pool()
    
    if not pool.has_keys(model):
        # Fallback to OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(api_key=openai_key)
        # Map models if needed
        target_model = "gpt-4o-mini"
        kw = dict(model=target_model, messages=messages, max_tokens=max_tokens, temperature=temperature)
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
