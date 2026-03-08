"""
Review existing MC questions against the word-count guidelines:
  - question statement: ideally ≤ 20 words
  - each option: ideally ≤ 15 words

Questions/options that exceed these targets are sent to Claude for tightening.
The DB is updated in-place.
"""

import asyncio
import json
import os
import re

import aiosqlite
from dotenv import load_dotenv

load_dotenv()

import anthropic

DB_PATH = "quizbase.db"

REVIEW_PROMPT = """\
You are editing a multiple-choice quiz question for conciseness.

Guidelines:
- Question statement: ideally under 20 words. Shorten if possible without losing meaning.
- Each answer option: ideally under 15 words. Condense if possible without losing accuracy.
- Keep all 4 options. Keep exactly 1 correct answer (is_correct: true).
- Do not change the factual content — only make the wording more concise.

Current question:
{question_json}

Return ONLY a JSON object in exactly this shape (no markdown, no explanation):
{{
  "statement": "...",
  "options": [
    {{"text": "...", "is_correct": true/false}},
    {{"text": "...", "is_correct": true/false}},
    {{"text": "...", "is_correct": true/false}},
    {{"text": "...", "is_correct": true/false}}
  ]
}}
"""


def word_count(text: str) -> int:
    return len(text.split())


def needs_review(statement: str, options: list[dict]) -> bool:
    if word_count(statement) > 20:
        return True
    return any(word_count(o["text"]) > 15 for o in options)


async def rewrite(client: anthropic.AsyncAnthropic, statement: str, options: list[dict]) -> dict | None:
    payload = {
        "statement": statement,
        "options": [{"text": o["text"], "is_correct": bool(o["is_correct"])} for o in options],
    }
    prompt = REVIEW_PROMPT.format(question_json=json.dumps(payload, indent=2))
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as exc:
        print(f"  [rewrite error] {exc}")
        return None


async def main():
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Fetch all MC questions
        cursor = await db.execute(
            "SELECT id, statement FROM questions WHERE type = 'multiple_choice'"
        )
        questions = [dict(r) for r in await cursor.fetchall()]
        print(f"Found {len(questions)} MC questions.")

        reviewed = 0
        updated = 0

        for q in questions:
            opt_cursor = await db.execute(
                "SELECT id, option_text, is_correct FROM question_options "
                "WHERE question_id = ? ORDER BY sort_order",
                (q["id"],),
            )
            opts = [dict(r) for r in await opt_cursor.fetchall()]
            opt_dicts = [{"id": o["id"], "text": o["option_text"], "is_correct": o["is_correct"]} for o in opts]

            if not needs_review(q["statement"], opt_dicts):
                continue

            reviewed += 1
            sw = word_count(q["statement"])
            long_opts = [o for o in opt_dicts if word_count(o["text"]) > 15]
            reasons = []
            if sw > 20:
                reasons.append(f"statement={sw}w")
            if long_opts:
                reasons.append(f"{len(long_opts)} option(s) over 15w")
            print(f"\nQ{q['id']} ({', '.join(reasons)}): {q['statement'][:80]}...")

            result = await rewrite(client, q["statement"], opt_dicts)
            if result is None:
                print("  → skipped (rewrite failed)")
                continue

            new_sw = word_count(result["statement"])
            new_long = [o for o in result["options"] if word_count(o["text"]) > 15]
            print(f"  → {new_sw}w statement, {len(new_long)} options still over 15w")
            print(f"  → \"{result['statement']}\"")

            # Update statement
            await db.execute(
                "UPDATE questions SET statement = ? WHERE id = ?",
                (result["statement"], q["id"]),
            )
            # Update each option (match by position / sort_order)
            for i, (old_opt, new_opt) in enumerate(zip(opt_dicts, result["options"])):
                await db.execute(
                    "UPDATE question_options SET option_text = ? WHERE id = ?",
                    (new_opt["text"], old_opt["id"]),
                )
            updated += 1

        await db.commit()

    print(f"\nDone. {reviewed} questions reviewed, {updated} updated.")


if __name__ == "__main__":
    asyncio.run(main())
