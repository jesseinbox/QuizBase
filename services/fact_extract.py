import io
import json
import os
import re
from typing import Optional

import anthropic

_client = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


FOCUS_LABELS = {
    "general":     "General (most important facts across all topics)",
    "theoretical": "Theoretical Concepts (principles, frameworks, models)",
    "scientific":  "Scientific & Technical (mechanisms, empirical findings, specifications)",
    "historical":  "Historical Facts (events, dates, people, causes, significance)",
    "definitions": "Key Definitions (terms, precise meanings, distinctions)",
    "processes":   "Processes & How-It-Works (sequences, cause-and-effect)",
}

FOCUS_INSTRUCTIONS = {
    "general":     "Extract the most important and varied facts across all topic areas.",
    "theoretical": "Focus on concepts, principles, frameworks, and theoretical models.",
    "scientific":  "Focus on scientific principles, technical mechanisms, empirical findings, and quantitative facts.",
    "historical":  "Focus on events, dates, people, causes, effects, and historical significance.",
    "definitions": "Focus on key terms, their precise definitions, and how they differ from related concepts.",
    "processes":   "Focus on how things work, step-by-step sequences, and cause-and-effect relationships.",
}

DEPTH_INSTRUCTIONS = {
    "broad":    "Prefer facts that capture major concepts over fine-grained details.",
    "specific": "Include specific details, statistics, named examples, and nuanced distinctions.",
}

EXTRACT_PROMPT = """\
You are extracting study facts from an educational document for a quiz app.

Document text:
---
{text}
---

Settings:
- Focus: {focus_label}
- Specificity: {depth_label}
- Extract up to {max_facts} facts (do not pad with low-quality facts to hit the maximum)

Instructions:
- {focus_instruction}
- {depth_instruction}
- Each fact must be a self-contained statement (1–2 sentences) that a student could be tested on.
- Facts must be specific and concrete — no vague summaries like "the document discusses...".
- Do not include procedural meta-statements or table-of-contents style entries.
{dedup_instruction}

Respond with ONLY a JSON array of strings, no markdown fences:
["fact 1", "fact 2", ...]
"""

DEDUP_INSTRUCTION_TEMPLATE = """\
- These facts already exist in the knowledge base — avoid extracting duplicates or \
near-duplicates of them:
{existing}"""


def extract_pdf_text(pdf_bytes: bytes, max_pages: int) -> tuple[str, int, int]:
    """Returns (text, pages_processed, total_pages). Raises on unreadable PDF."""
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    limit = min(max_pages, total) if max_pages > 0 else total
    parts = []
    for i in range(limit):
        page_text = reader.pages[i].extract_text() or ""
        parts.append(page_text)
    return "\n\n".join(parts), limit, total


async def extract_facts(
    text: str,
    max_facts: int,
    focus: str,
    depth: str,
    existing_facts: Optional[list[str]] = None,
) -> list[str]:
    client = _get_client()

    focus_label = FOCUS_LABELS.get(focus, FOCUS_LABELS["general"])
    depth_label = "Broad overview" if depth == "broad" else "Specific details"
    focus_instruction = FOCUS_INSTRUCTIONS.get(focus, FOCUS_INSTRUCTIONS["general"])
    depth_instruction = DEPTH_INSTRUCTIONS.get(depth, DEPTH_INSTRUCTIONS["broad"])

    if existing_facts:
        existing_str = "\n".join(f"  - {f}" for f in existing_facts[:40])
        dedup_instruction = DEDUP_INSTRUCTION_TEMPLATE.format(existing=existing_str)
    else:
        dedup_instruction = ""

    prompt = EXTRACT_PROMPT.format(
        text=text[:25000],  # ~6 000 tokens — keeps costs predictable
        focus_label=focus_label,
        depth_label=depth_label,
        focus_instruction=focus_instruction,
        depth_instruction=depth_instruction,
        max_facts=max_facts,
        dedup_instruction=dedup_instruction,
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    facts = json.loads(raw)
    if not isinstance(facts, list):
        raise ValueError("Unexpected response shape")
    return [str(f).strip() for f in facts[:max_facts] if str(f).strip()]
