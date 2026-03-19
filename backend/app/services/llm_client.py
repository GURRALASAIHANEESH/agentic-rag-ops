import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator

import httpx
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


# ── Abstract interface ────────────────────────────────────────────────────────
# Every LLM backend must implement this. Swapping providers = swap the class.

class LLMClient(ABC):
    """
    Base interface for all LLM providers.
    All implementations must support both streaming and non-streaming.
    """

    @abstractmethod
    async def generate(self, prompt: str, system: str = "") -> str:
        """Non-streaming: returns the full response as a string."""
        ...

    @abstractmethod
    async def stream(
        self, prompt: str, system: str = ""
    ) -> AsyncGenerator[str, None]:
        """Streaming: yields token deltas one at a time."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the model identifier string for logging/metrics."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the provider name: 'local' | 'openai' | 'groq'."""
        ...


# ── Local llama.cpp client ────────────────────────────────────────────────────
# Talks to llama.cpp HTTP server started via llm/run_server.sh
# Compatible with OpenAI /v1/completions API format (llama.cpp supports this)

class LocalLlamaClient(LLMClient):
    """
    Client for a local llama.cpp server running on LLAMA_SERVER_URL.
    Uses the /v1/chat/completions endpoint (OpenAI-compatible).

    Start the server first:
        cd llm && bash run_server.sh
    """

    def __init__(self):
        self._base_url = settings.LLAMA_SERVER_URL
        self._model = settings.LLAMA_MODEL_NAME
        self._max_tokens = settings.LLAMA_MAX_TOKENS
        self._temperature = settings.LLAMA_TEMPERATURE
        # httpx async client reused across calls — avoids connection overhead
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(120.0),   # local models can be slow
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "local"

    def _build_messages(self, prompt: str, system: str) -> list[dict]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(self, prompt: str, system: str = "") -> str:
        """Non-streaming call to local llama.cpp server."""
        payload = {
            "model": self._model,
            "messages": self._build_messages(prompt, system),
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "stream": False,
        }
        try:
            response = await self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            logger.error("llama_generate_failed", error=str(e))
            raise RuntimeError(f"Local LLM call failed: {e}") from e

    async def stream(
        self, prompt: str, system: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        Streaming call — yields token deltas as they arrive from llama.cpp.
        llama.cpp sends SSE lines like: data: {"choices":[{"delta":{"content":"hi"}}]}
        """
        payload = {
            "model": self._model,
            "messages": self._build_messages(prompt, system),
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "stream": True,
        }
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError):
                        # Malformed chunk — skip silently, don't crash stream
                        continue
        except httpx.HTTPError as e:
            logger.error("llama_stream_failed", error=str(e))
            raise RuntimeError(f"Local LLM stream failed: {e}") from e

    async def close(self):
        await self._client.aclose()


# ── OpenAI client ─────────────────────────────────────────────────────────────

class OpenAIClient(LLMClient):
    """
    Client for OpenAI API (GPT-4o-mini by default).
    Set LLM_PROVIDER=openai and OPENAI_API_KEY in .env to activate.
    """

    def __init__(self):
        self._model = settings.OPENAI_MODEL
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=settings.LLAMA_MAX_TOKENS,
            temperature=settings.LLAMA_TEMPERATURE,
            stream=False,
        )
        return response.choices[0].message.content

    async def stream(
        self, prompt: str, system: str = ""
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=settings.LLAMA_MAX_TOKENS,
            temperature=settings.LLAMA_TEMPERATURE,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Groq client ───────────────────────────────────────────────────────────────
# Groq offers a generous free tier — great zero-cost alternative to local LLM

class GroqClient(LLMClient):
    """
    Client for Groq API (llama3-8b-8192 by default — free tier available).
    Set LLM_PROVIDER=groq and GROQ_API_KEY in .env to activate.
    Groq uses the OpenAI-compatible SDK, so this is nearly identical to OpenAI.
    """

    def __init__(self):
        from groq import AsyncGroq
        self._model = settings.GROQ_MODEL
        self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "groq"

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=settings.LLAMA_MAX_TOKENS,
            temperature=settings.LLAMA_TEMPERATURE,
        )
        return response.choices[0].message.content

    async def stream(
        self, prompt: str, system: str = ""
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=settings.LLAMA_MAX_TOKENS,
            temperature=settings.LLAMA_TEMPERATURE,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Factory function ──────────────────────────────────────────────────────────
# Single place to swap providers — toggle via LLM_PROVIDER env var.

def get_llm_client() -> LLMClient:
    """
    Returns the correct LLMClient based on LLM_PROVIDER setting.

    To swap providers at any time:
        Set LLM_PROVIDER=local  → uses LocalLlamaClient  (zero cost)
        Set LLM_PROVIDER=openai → uses OpenAIClient      (paid)
        Set LLM_PROVIDER=groq   → uses GroqClient        (free tier)

    Used as a FastAPI dependency:
        client: LLMClient = Depends(get_llm_client)
    """
    provider = settings.LLM_PROVIDER
    logger.info("llm_client_selected", provider=provider)

    if provider == "local":
        return LocalLlamaClient()
    elif provider == "openai":
        return OpenAIClient()
    elif provider == "groq":
        return GroqClient()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Valid options: local | openai | groq"
        )
