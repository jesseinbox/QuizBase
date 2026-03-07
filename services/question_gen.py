import json
import os
import re

import anthropic
import aiosqlite

from database import DB_PATH

_client = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


PROMPT = """\
You are a quiz question generator for a study app.

Given this fact:
"{fact}"

Use web search if helpful to verify accuracy or find closely related information.

Generate exactly 5 true/false statements derived from this fact and directly related knowledge.
Rules:
- Aim for roughly 2-3 true and 2-3 false statements (mix them up)
- False statements must be plausible but clearly wrong
- Keep each statement to 1-2 sentences
- Do NOT use phrases like "According to the fact…" — write standalone statements

Respond with ONLY a JSON array, no markdown fences, no explanation:
[
  {{"statement": "...", "is_true": true}},
  {{"statement": "...", "is_true": false}},
  ...
]
"""


async def generate_and_store(fact_id: int, fact_content: str) -> None:
    """Generate 5 T/F questions for a fact and persist them. Silently no-ops on error."""
    try:
        questions = await _generate(fact_content)
    except Exception as exc:
        print(f"[question_gen] generation failed for fact {fact_id}: {exc}")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.executemany(
                "INSERT INTO questions (fact_id, statement, is_true) VALUES (?, ?, ?)",
                [(fact_id, q["statement"], int(q["is_true"])) for q in questions],
            )
            await db.commit()
    except Exception as exc:
        print(f"[question_gen] db write failed for fact {fact_id}: {exc}")


MC_PROMPT = """\
You are a quiz question generator for a study app.

Given this fact:
"{fact}"

Use web search if helpful to verify or supplement the fact.

Generate exactly 1 multiple choice question based on this fact. It should be the \
same difficulty or harder than a basic true/false question on the topic.

Requirements:
- A clear question prompt (1-2 sentences)
- Exactly 4 answer options
- Exactly 1 correct answer
- 3 plausible but clearly incorrect distractors
- Do not make the correct answer obvious by position or length

Respond with ONLY a JSON object, no markdown fences:
{{
  "statement": "...",
  "options": [
    {{"text": "...", "is_correct": true}},
    {{"text": "...", "is_correct": false}},
    {{"text": "...", "is_correct": false}},
    {{"text": "...", "is_correct": false}}
  ]
}}
"""


async def generate_and_store_mc(fact_id: int, fact_content: str) -> None:
    """Generate 1 MC question for a fact and persist it with its options."""
    try:
        client = _get_client()
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": MC_PROMPT.format(fact=fact_content)}],
        )
        text = ""
        for block in reversed(response.content):
            if block.type == "text":
                text = block.text.strip()
                break
        if not text:
            raise ValueError("No text block in response")
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        q = json.loads(text)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cursor = await db.execute(
                "INSERT INTO questions (fact_id, statement, is_true, type) VALUES (?, ?, 0, 'multiple_choice')",
                (fact_id, q["statement"]),
            )
            qid = cursor.lastrowid
            for i, opt in enumerate(q["options"][:4]):
                await db.execute(
                    "INSERT INTO question_options (question_id, option_text, is_correct, sort_order) VALUES (?, ?, ?, ?)",
                    (qid, opt["text"], int(opt["is_correct"]), i),
                )
            await db.commit()
    except Exception as exc:
        print(f"[question_gen] MC generation failed for fact {fact_id}: {exc}")


async def _generate(fact_content: str) -> list[dict]:
    client = _get_client()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": PROMPT.format(fact=fact_content),
        }],
    )

    # Extract the last text block (model's final answer after any tool use)
    text = ""
    for block in reversed(response.content):
        if block.type == "text":
            text = block.text.strip()
            break

    if not text:
        raise ValueError("No text block in response")

    # Strip accidental markdown fences
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    questions = json.loads(text)
    if not isinstance(questions, list) or len(questions) == 0:
        raise ValueError("Unexpected response shape")
    return questions[:5]
