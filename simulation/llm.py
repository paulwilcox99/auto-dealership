"""OpenAI note generation with in-memory cache and template fallback."""

import hashlib
import random
from datetime import date
from typing import Optional

from config import OPENAI_API_KEY, OPENAI_MODEL, LLM_MAX_CALLS_PER_WORKER
from data.note_templates import NOTE_TEMPLATES

# In-memory cache: hash(customer_name + context_hint) → note text
_cache: dict[str, str] = {}

# Per-worker call counter (reset by workers/__init__.py before each worker run)
_worker_call_count: int = 0


def reset_worker_call_count() -> None:
    global _worker_call_count
    _worker_call_count = 0


def _cache_key(customer_name: str, context_hint: str) -> str:
    raw = f"{customer_name}|{context_hint}"
    return hashlib.md5(raw.encode()).hexdigest()


def _fallback_note(customer_name: str, sim_date: date) -> str:
    """Return a random filled-in template note."""
    template = random.choice(NOTE_TEMPLATES)
    return template.format(name=customer_name, date=sim_date.strftime("%B %d, %Y"))


def create_note(
    customer_name: str,
    existing_notes: list,
    context_hint: str,
    sim_date: date,
) -> str:
    """Generate a realistic dealership note.

    Args:
        customer_name:  Customer's full name.
        existing_notes: List of prior note dicts [{date, text}].
        context_hint:   Short phrase describing current context (e.g. 'lead contacted').
        sim_date:       Current simulation date.

    Returns:
        A 1–3 sentence note string.
    """
    global _worker_call_count

    key = _cache_key(customer_name, context_hint)
    if key in _cache:
        return _cache[key]

    # Use fallback if no API key, or call limit reached
    if not OPENAI_API_KEY or _worker_call_count >= LLM_MAX_CALLS_PER_WORKER:
        note = _fallback_note(customer_name, sim_date)
        _cache[key] = note
        return note

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        prior_notes_text = ""
        if existing_notes:
            snippets = [f"- {n['date']}: {n['text']}" for n in existing_notes[-3:]]
            prior_notes_text = "\nPrior notes:\n" + "\n".join(snippets)

        prompt = (
            f"You are a car dealership employee writing a brief CRM/LMS note.\n"
            f"Customer: {customer_name}\n"
            f"Date: {sim_date.strftime('%B %d, %Y')}\n"
            f"Context: {context_hint}{prior_notes_text}\n\n"
            f"Write a realistic 1–3 sentence note in first person from the employee's perspective. "
            f"Be specific and natural. Do not use bullet points."
        )

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.7,
        )
        note = response.choices[0].message.content.strip()
        _worker_call_count += 1
        _cache[key] = note
        return note

    except Exception:
        note = _fallback_note(customer_name, sim_date)
        _cache[key] = note
        return note
