import json
import os
import re

import anthropic

_client = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


GRADE_PROMPT = """\
You are grading a short-answer quiz response.

Question: {statement}

Source fact the question is based on:
{fact_content}

Key concepts a correct answer should cover:
{grading_notes}

Student's answer:
"{user_answer}"

Evaluate whether the answer demonstrates genuine understanding of the key concepts. \
Credit understanding over exact wording. A passing answer should address the substance \
of the question and show familiarity with the relevant ideas — it does not need to be \
perfectly worded. A failing answer is one that is blank, off-topic, or fundamentally wrong.

Respond with ONLY a JSON object, no markdown:
{{"correct": true/false, "feedback": "1-2 sentences. If correct, affirm what they got right. If wrong, briefly hint at what was missing without giving the answer away."}}
"""


async def grade_short_answer(
    statement: str,
    fact_content: str,
    grading_notes: str,
    user_answer: str,
) -> dict:
    """Returns {"correct": bool, "feedback": str}."""
    client = _get_client()
    prompt = GRADE_PROMPT.format(
        statement=statement,
        fact_content=fact_content,
        grading_notes=grading_notes or "Cover the main ideas expressed in the source fact.",
        user_answer=user_answer,
    )
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as exc:
        print(f"[question_grade] grading error: {exc}")
        return {"correct": False, "feedback": "Could not grade your answer — please try again."}
