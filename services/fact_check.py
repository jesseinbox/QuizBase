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


FACT_CHECK_PROMPT = """\
You are a fact-checker for a study app. Verify whether the following statement is factually accurate.

Statement: "{fact}"

Use web search if you are uncertain about the claim.

Guidelines:
- Err strongly on the side of accepting — only flag if you are confident the core claim is wrong
- Accept subjective statements, opinions, interpretations, and simplified explanations
- Accept facts that are context-dependent or lack nuance, unless the core claim is outright wrong
- Do not flag for incompleteness — only flag demonstrable factual inaccuracies
- Historical facts, scientific principles, and established knowledge should generally be accepted

Respond with ONLY a JSON object, no markdown fences:
{{"accurate": true, "concern": ""}}
or
{{"accurate": false, "concern": "One sentence describing the specific factual error"}}
"""


async def check_and_flag_fact(fact_id: int, fact_content: str) -> None:
    """Verify a fact's accuracy and set accuracy_flag if inaccurate. Silently no-ops on error."""
    try:
        client = _get_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": FACT_CHECK_PROMPT.format(fact=fact_content)}],
        )
        text = ""
        for block in reversed(response.content):
            if block.type == "text":
                text = block.text.strip()
                break
        if not text:
            return
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        result = json.loads(text)

        if not result.get("accurate", True):
            concern = result.get("concern") or "Flagged as potentially inaccurate"
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE facts SET accuracy_flag = ? WHERE id = ?",
                    (concern, fact_id),
                )
                await db.commit()
    except Exception as exc:
        print(f"[fact_check] check failed for fact {fact_id}: {exc}")
