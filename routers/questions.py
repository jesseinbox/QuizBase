from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from database import get_db
from services.question_gen import generate_and_store_mc

router = APIRouter(prefix="/api/questions", tags=["questions"])

INTERVALS = {1: 7, 2: 30, 3: 180}
DEFAULT_INTERVAL = 365


def _interval_days(correct_count: int) -> int:
    return INTERVALS.get(correct_count, DEFAULT_INTERVAL)


def _next_due(correct_count: int) -> tuple[str, int]:
    days = _interval_days(correct_count)
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S"), days


@router.get("")
async def list_questions(
    topic_id: Optional[int] = Query(None),
    course_id: Optional[int] = Query(None),
    fact_id: Optional[int] = Query(None),
    due_only: bool = Query(False),
    db=Depends(get_db),
):
    conditions = []
    params = []
    if fact_id is not None:
        conditions.append("q.fact_id = ?")
        params.append(fact_id)
    if topic_id is not None:
        conditions.append("f.topic_id = ?")
        params.append(topic_id)
    if course_id is not None:
        conditions.append("f.course_id = ?")
        params.append(course_id)
    if due_only:
        conditions.append("(p.next_due_at IS NULL OR p.next_due_at <= datetime('now'))")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cursor = await db.execute(f"""
        SELECT q.id, q.fact_id, q.statement, q.is_true,
               COALESCE(q.type, 'true_false') AS type,
               q.created_at,
               f.content AS fact_content, f.topic_id,
               t.name AS topic_name,
               COALESCE(p.correct_count, 0) AS correct_count,
               p.next_due_at
        FROM questions q
        JOIN facts f ON f.id = q.fact_id
        JOIN topics t ON t.id = f.topic_id
        LEFT JOIN question_progress p ON p.question_id = q.id
        {where}
        ORDER BY q.fact_id, q.id
    """, params)
    rows = [dict(r) for r in await cursor.fetchall()]

    # Attach options for MC questions
    mc_ids = [r["id"] for r in rows if r["type"] == "multiple_choice"]
    if mc_ids:
        placeholders = ",".join("?" * len(mc_ids))
        opt_cursor = await db.execute(
            f"SELECT question_id, option_text, is_correct, sort_order "
            f"FROM question_options WHERE question_id IN ({placeholders}) ORDER BY sort_order",
            mc_ids,
        )
        opts_by_q: dict[int, list] = {}
        for opt in await opt_cursor.fetchall():
            opt = dict(opt)
            opts_by_q.setdefault(opt["question_id"], []).append(opt)
        for r in rows:
            r["options"] = opts_by_q.get(r["id"], []) if r["type"] == "multiple_choice" else []
    else:
        for r in rows:
            r["options"] = []

    return rows


class AnswerBody(BaseModel):
    correct: bool


@router.post("/{question_id}/answer")
async def record_answer(
    question_id: int,
    body: AnswerBody,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    q_row = await (await db.execute(
        "SELECT id, COALESCE(type, 'true_false') AS type, fact_id FROM questions WHERE id = ?",
        (question_id,)
    )).fetchone()
    if not q_row:
        raise HTTPException(status_code=404, detail="Question not found")

    if not body.correct:
        return {"correct_count": None, "next_due_at": None, "interval_days": None}

    prog = await (await db.execute(
        "SELECT correct_count FROM question_progress WHERE question_id = ?", (question_id,)
    )).fetchone()

    prev_count = prog["correct_count"] if prog else 0
    new_count = prev_count + 1
    due_str, days = _next_due(new_count)

    await db.execute("""
        INSERT INTO question_progress (question_id, correct_count, next_due_at, last_answered_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(question_id) DO UPDATE SET
            correct_count    = ?,
            next_due_at      = ?,
            last_answered_at = CURRENT_TIMESTAMP,
            updated_at       = CURRENT_TIMESTAMP
    """, (question_id, new_count, due_str, new_count, due_str))
    await db.commit()

    # On first correct answer to a T/F question, generate an MC question for the same fact
    if prev_count == 0 and q_row["type"] == "true_false":
        fact = await (await db.execute(
            "SELECT content FROM facts WHERE id = ?", (q_row["fact_id"],)
        )).fetchone()
        if fact:
            background_tasks.add_task(generate_and_store_mc, q_row["fact_id"], fact["content"])

    return {"correct_count": new_count, "next_due_at": due_str, "interval_days": days}
