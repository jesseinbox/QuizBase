import json
import os
import re

import aiosqlite
import anthropic

from database import DB_PATH

_client = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


DUPLICATE_PROMPT = """\
You are checking whether a new fact is a duplicate of any existing facts in a study flashcard app.

New fact: "{new_fact}"

Existing facts in this topic ({count} total):
{existing_facts}

A duplicate means the new fact covers the same core concept or claim as an existing fact closely \
enough that they would likely produce the same or very similar quiz questions.

Guidelines:
- Flag as duplicate ONLY if the core claim substantially overlaps with an existing fact
- Facts can share the same topic but cover different aspects — that is NOT a duplicate
- A paraphrase of an existing fact IS a duplicate
- A more specific or more detailed version of the same claim IS a duplicate
- Different examples or applications of the same general principle are NOT duplicates

Respond with ONLY a JSON object, no markdown fences:
{{"is_duplicate": false}}
or
{{"is_duplicate": true, "matching_fact": "copy of the matching existing fact (max 120 chars)"}}
"""


async def check_and_flag_duplicate(fact_id: int, fact_content: str, topic_id: int) -> None:
    """Compare a new fact against existing facts in the same topic and flag if duplicate."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT content FROM facts WHERE topic_id = ? AND id != ? ORDER BY id LIMIT 100",
                (topic_id, fact_id),
            )
            existing = [row["content"] for row in await cursor.fetchall()]

        if not existing:
            return

        numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(existing))
        client = _get_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": DUPLICATE_PROMPT.format(
                    new_fact=fact_content,
                    count=len(existing),
                    existing_facts=numbered,
                ),
            }],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                break
        if not text:
            return

        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        result = json.loads(text)

        if result.get("is_duplicate"):
            matching = (result.get("matching_fact") or "an existing fact")[:120]
            flag_msg = f'Possible duplicate of: "{matching}"'
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE facts SET accuracy_flag = ? WHERE id = ?",
                    (flag_msg, fact_id),
                )
                await db.commit()

    except Exception as exc:
        print(f"[fact_duplicate] check failed for fact {fact_id}: {exc}")


BULK_DUPLICATE_PROMPT = """\
You are identifying duplicate facts in a study flashcard app.

Below is a numbered list of facts. Identify any pairs where one is a duplicate of another — \
meaning they cover the same core claim and would produce the same or very similar quiz questions.

Facts:
{facts}

Rules:
- A duplicate: paraphrase of the same claim, or a more detailed version of the same fact
- NOT a duplicate: different aspects of a topic, different examples, different applications
- For each duplicate pair, "keep" is the lower-numbered (earlier) fact, "flag" is the duplicate

Respond with ONLY a JSON object, no markdown fences:
{{"pairs": [{{"keep": 1, "flag": 3, "reason": "brief reason"}}, ...]}}
If no duplicates found: {{"pairs": []}}
"""


async def bulk_scan_topic(topic_id: int, facts: list[dict]) -> list[tuple[int, str]]:
    """
    Scan a list of facts for duplicates in a single Haiku call.
    facts: list of {"id": int, "content": str}
    Returns list of (fact_id_to_flag, matching_content) tuples.
    """
    if len(facts) < 2:
        return []

    numbered = "\n".join(f"{i + 1}. {f['content']}" for i, f in enumerate(facts))
    client = _get_client()
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": BULK_DUPLICATE_PROMPT.format(facts=numbered),
        }],
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            break
    if not text:
        return []

    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    result = json.loads(text)

    flagged = []
    for pair in result.get("pairs", []):
        keep_idx = pair.get("keep", 1) - 1   # convert 1-based to 0-based
        flag_idx = pair.get("flag", 1) - 1
        if 0 <= keep_idx < len(facts) and 0 <= flag_idx < len(facts) and keep_idx != flag_idx:
            keep_content = facts[keep_idx]["content"][:120]
            flag_id = facts[flag_idx]["id"]
            flagged.append((flag_id, keep_content))

    return flagged
