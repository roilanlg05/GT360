"""
Utilidad para generar nombres cortos de hoteles usando Groq (gpt-oss-120b).
"""
import httpx
import logging
import re
import os

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT = """Shorten this hotel name to max 25 characters (30 absolute max if impossible otherwise). Remove the city, state, country, location descriptors ("Downtown", "at the Convention Center", "near the Airport", etc.) and generic suffixes ("Hotel", "Hotel & Suites", "Inn & Suites", "Resort") when a recognizable brand remains. Use abbreviations if needed ("Courtyard by Marriott" -> "Courtyard Marriott"). If the name starts with "The", keep it (e.g. "The Galt House", "The Seelbach Hilton"). Keep the brand recognizable. Return ONLY the short name."""


async def generate_short_name(full_name: str, city_name: str | None = None) -> str:
    """
    Genera un nombre corto para un hotel usando Groq API (gpt-oss-120b).
    Fallback: reglas de texto si la API falla.
    """
    if not full_name or not full_name.strip():
        return full_name

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY no configurada, usando fallback de reglas de texto")
        return _fallback_short_name(full_name, city_name)

    user_msg = f"Hotel: {full_name.strip()}"
    if city_name:
        user_msg += f"\nCity: {city_name.strip()}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "user", "content": f"{PROMPT}\n\n{user_msg}"},
                    ],
                    "temperature": 1,
                    "max_completion_tokens": 100,
                    "reasoning_effort": "low",
                },
            )
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip().strip('"\'')

            if len(result) < 2 or len(result) > len(full_name):
                return _fallback_short_name(full_name, city_name)

            # Guardia final: si el LLM devolvió algo >30, truncar al último espacio
            if len(result) > 30:
                truncated = result[:30].rsplit(' ', 1)[0]
                return truncated if len(truncated) >= 3 else result[:30]

            return result

    except Exception as e:
        logger.warning(f"Groq API error para '{full_name}': {e}. Usando fallback.")
        return _fallback_short_name(full_name, city_name)


# ── Fallback con reglas de texto ──

_PREPOSITIONAL_PATTERNS = re.compile(
    r'\s+(?:at|near|by|next to|across from|opposite|overlooking|off|on)\s+the\s+.+$',
    re.IGNORECASE
)

_OPTIONAL_SUFFIXES = re.compile(
    r'\s+(?:Hotel(?:\s*&\s*Suites)?|Inn(?:\s*&\s*Suites)?|Suites|Resort(?:\s*&\s*Spa)?|Lodge|Motel)$',
    re.IGNORECASE
)


def _fallback_short_name(full_name: str, city_name: str | None = None) -> str:
    """Fallback basado en reglas de texto cuando Groq no está disponible."""
    name = full_name.strip()

    if city_name and city_name.strip():
        escaped = re.escape(city_name.strip())
        name = re.sub(r'\b' + escaped + r'\b', '', name, flags=re.IGNORECASE)

    name = _PREPOSITIONAL_PATTERNS.sub('', name)
    name = re.sub(r'\s*,\s*', ' ', name)
    name = re.sub(r'\s*-\s*$', '', name)
    name = re.sub(r'^\s*-\s*', '', name)
    name = re.sub(r'\s{2,}', ' ', name)
    name = name.strip()

    candidate = _OPTIONAL_SUFFIXES.sub('', name).strip()
    if len(candidate) >= 3:
        name = candidate

    if len(name) < 3:
        return full_name.strip()[:30]

    return name[:30] if len(name) > 30 else name
