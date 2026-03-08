"""Verify a flagged question against its source fact, then replace it if invalid."""
import json
import re

import aiosqlite

from database import DB_PATH
from services.question_gen import _get_client, generate_and_store_mc

TF_VERIFY_PROMPT = """\
You are reviewing a true/false quiz question that a user has flagged. Apply strict scrutiny.

Source fact (the only basis for this question): "{fact}"

Quiz question:
  Statement: "{statement}"
  Marked as: {answer}

User's flag reason: {reason}

Strict criteria — the question is only valid if ALL of the following are true:
1. The true/false answer is unambiguously correct
2. The statement is directly and explicitly grounded in the source fact as written — \
not merely related to the same general topic
3. The statement does not introduce concepts, details, or specifics that go beyond \
what is stated in the source fact
4. The statement is clear and unambiguous

When in doubt, rule invalid. The user's flag is a strong signal — do not keep a \
question unless you are confident it passes all criteria above.

Use web search only to verify factual accuracy, not to broaden the scope of the fact.

Respond with ONLY a JSON object, no other text:
{{"valid": true, "explanation": "..."}}
"""

MC_VERIFY_PROMPT = """\
You are reviewing a multiple choice quiz question that a user has flagged. Apply strict scrutiny.

Source fact (the only basis for this question): "{fact}"

Quiz question: "{statement}"
Options:
{options}

User's flag reason: {reason}

Strict criteria — the question is only valid if ALL of the following are true:
1. Exactly one option is unambiguously correct
2. The correct answer is directly and explicitly grounded in the source fact as written
3. The question does not introduce concepts, details, or specifics that go beyond \
what is stated in the source fact
4. Distractors are plausible but clearly wrong
5. The question is clear and unambiguous

When in doubt, rule invalid. The user's flag is a strong signal — do not keep a \
question unless you are confident it passes all criteria above.

Use web search only to verify factual accuracy, not to broaden the scope of the fact.

Respond with ONLY a JSON object, no other text:
{{"valid": true, "explanation": "..."}}
"""

TF_REPLACE_PROMPT = """\
You are a quiz question generator.

Source fact: "{fact}"

Generate exactly 1 replacement true/false statement for a question that was removed \
because: {reason}

Avoid the same issue. The statement must be clear, directly related to the fact, \
and have a verifiably correct true/false answer.

Respond with ONLY a JSON object, no other text:
{{"statement": "...", "is_true": true}}
"""

MC_REPLACE_PROMPT = """\
You are a quiz question generator.

Source fact: "{fact}"

Generate exactly 1 replacement multiple choice question for one that was removed \
because: {reason}

Requirements:
- Clear question prompt (1-2 sentences)
- Exactly 4 answer options, exactly 1 correct
- Plausible but clearly wrong distractors
- Avoid the same issue as the removed question

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


def _extract_text(response) -> str:
    for block in reversed(response.content):
        if block.type == "text":
            text = block.text.strip()
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
            return text
    return ""


async def verify_and_reprocess(question_id: int, flag_id: int) -> None:
    """Verify a flagged question. If invalid, delete it and insert a replacement."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")

            row = await (await db.execute("""
                SELECT q.id, q.statement, q.is_true, q.fact_id,
                       COALESCE(q.type, 'true_false') AS type,
                       f.content AS fact_content,
                       fl.reason_type, fl.reason_text
                FROM questions q
                JOIN facts f ON f.id = q.fact_id
                JOIN flags fl ON fl.id = ?
                WHERE q.id = ?
            """, (flag_id, question_id))).fetchone()

            if not row:
                return
            row = dict(row)

            options = []
            if row["type"] == "multiple_choice":
                opt_rows = await (await db.execute(
                    "SELECT option_text, is_correct FROM question_options WHERE question_id = ? ORDER BY sort_order",
                    (question_id,)
                )).fetchall()
                options = [dict(r) for r in opt_rows]

        reason = row["reason_type"].replace("_", " ")
        if row["reason_text"]:
            reason += f": {row['reason_text']}"

        client = _get_client()
        is_mc = row["type"] == "multiple_choice"

        if is_mc:
            letters = "ABCD"
            options_text = "\n".join(
                f"  {letters[i]}. {o['option_text']}{' ← CORRECT' if o['is_correct'] else ''}"
                for i, o in enumerate(options)
            )
            prompt = MC_VERIFY_PROMPT.format(
                fact=row["fact_content"],
                statement=row["statement"],
                options=options_text,
                reason=reason,
            )
        else:
            prompt = TF_VERIFY_PROMPT.format(
                fact=row["fact_content"],
                statement=row["statement"],
                answer="TRUE" if row["is_true"] else "FALSE",
                reason=reason,
            )

        verify_resp = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(_extract_text(verify_resp))
        valid = bool(result.get("valid", True))

        explanation = result.get("explanation", "")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                "UPDATE flags SET verdict = ?, verdict_explanation = ? WHERE id = ?",
                ("dismissed" if valid else "confirmed", explanation, flag_id),
            )

            if not valid:
                fact_id = row["fact_id"]
                await db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
                await db.commit()

                if is_mc:
                    # generate_and_store_mc opens its own connection
                    await generate_and_store_mc(fact_id, row["fact_content"])
                    return
                else:
                    replace_resp = await client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=512,
                        tools=[{"type": "web_search_20250305", "name": "web_search"}],
                        messages=[{"role": "user", "content": TF_REPLACE_PROMPT.format(
                            fact=row["fact_content"], reason=reason,
                        )}],
                    )
                    new_q = json.loads(_extract_text(replace_resp))
                    await db.execute(
                        "INSERT INTO questions (fact_id, statement, is_true) VALUES (?, ?, ?)",
                        (fact_id, new_q["statement"], int(new_q["is_true"])),
                    )

            await db.commit()

    except Exception as exc:
        print(f"[question_verify] failed for question {question_id}: {exc}")
