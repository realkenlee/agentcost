"""Public list prices — USD per 1M tokens (input, output)."""
from __future__ import annotations

_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7":               (15.0,  75.0),
    "claude-opus-4-5":               (15.0,  75.0),
    "claude-sonnet-4-6":             (3.0,   15.0),
    "claude-sonnet-4-5":             (3.0,   15.0),
    "claude-haiku-4-5":              (0.80,  4.0),
    "claude-haiku-4-5-20251001":     (0.80,  4.0),
    "claude-3-5-sonnet-20241022":    (3.0,   15.0),
    "claude-3-5-haiku-20241022":     (0.80,  4.0),
    "claude-3-opus-20240229":        (15.0,  75.0),

    # OpenAI
    "gpt-4o":                        (2.50,  10.0),
    "gpt-4o-mini":                   (0.15,  0.60),
    "o1":                            (15.0,  60.0),
    "o1-mini":                       (1.10,  4.40),
    "o3":                            (10.0,  40.0),
    "o3-mini":                       (1.10,  4.40),
    "gpt-4-turbo":                   (10.0,  30.0),

    # Google
    "gemini-2.0-flash":              (0.10,  0.40),
    "gemini-1.5-pro":                (1.25,  5.0),
    "gemini-1.5-flash":              (0.075, 0.30),

    # Groq
    "llama-3.3-70b-versatile":       (0.59,  0.79),
    "llama-3.1-8b-instant":          (0.05,  0.08),
    "gemma2-9b-it":                  (0.20,  0.20),

    # Mistral
    "mistral-large-latest":          (2.0,   6.0),
    "mistral-small-latest":          (0.10,  0.30),
}

# Prefix fallbacks — match on model name prefix when exact key missing
_PREFIX_FALLBACKS: list[tuple[str, tuple[float, float]]] = [
    ("claude-opus",   (15.0, 75.0)),
    ("claude-sonnet", (3.0,  15.0)),
    ("claude-haiku",  (0.80, 4.0)),
    ("gpt-4o-mini",   (0.15, 0.60)),
    ("gpt-4o",        (2.50, 10.0)),
    ("gpt-4",         (10.0, 30.0)),
    ("o1",            (15.0, 60.0)),
    ("o3",            (10.0, 40.0)),
    ("gemini-2",      (0.10, 0.40)),
    ("gemini-1.5",    (1.25, 5.0)),
    ("llama-3.3",     (0.59, 0.79)),
    ("llama-3.1",     (0.05, 0.08)),
    ("llama",         (0.10, 0.10)),
    ("mistral",       (1.0,  3.0)),
]


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return USD cost or None if model is unknown."""
    model = model.lower().strip()
    # Strip provider prefixes like "anthropic/", "openai/", "groq/"
    if "/" in model:
        model = model.split("/", 1)[1]

    price = _PRICES.get(model)
    if price is None:
        for prefix, p in _PREFIX_FALLBACKS:
            if model.startswith(prefix):
                price = p
                break

    if price is None:
        return None

    input_per_mtok, output_per_mtok = price
    return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000
