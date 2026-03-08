from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db
from services.question_verify import verify_and_reprocess

router = APIRouter(prefix="/api/questions", tags=["flags"])

VALID_REASONS = {"wrong_answer", "not_related", "no_sense", "other"}

REASON_LABELS = {
    "wrong_answer": "Wrong answer",
    "not_related":  "Not covered",
    "no_sense":     "Doesn't make sense",
    "other":        "Other",
}


class FlagCreate(BaseModel):
    reason_type: str
    reason_text: Optional[str] = None


class OverrideBody(BaseModel):
    action: str  # "remove" | "keep"


@router.post("/{question_id}/flag", status_code=201)
async def flag_question(
    question_id: int,
    body: FlagCreate,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    if body.reason_type not in VALID_REASONS:
        raise HTTPException(status_code=422, detail="Invalid reason_type")

    row = await (await db.execute(
        "SELECT id FROM questions WHERE id = ?", (question_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Question not found")

    cursor = await db.execute(
        "INSERT INTO flags (question_id, reason_type, reason_text) VALUES (?, ?, ?)",
        (question_id, body.reason_type, body.reason_text or None),
    )
    await db.commit()
    flag_id = cursor.lastrowid

    background_tasks.add_task(verify_and_reprocess, question_id, flag_id)
    return {"flag_id": flag_id, "status": "pending"}


@router.get("/flags")
async def list_flags(db=Depends(get_db)):
    cursor = await db.execute("""
        SELECT fl.id, fl.question_id, fl.reason_type, fl.reason_text,
               fl.verdict, fl.verdict_explanation, fl.created_at,
               q.statement, COALESCE(q.type, 'true_false') AS type, q.is_true,
               f.content AS fact_content,
               t.name AS topic_name
        FROM flags fl
        JOIN questions q ON q.id = fl.question_id
        JOIN facts f ON f.id = q.fact_id
        JOIN topics t ON t.id = f.topic_id
        ORDER BY fl.created_at DESC
    """)
    rows = [dict(r) for r in await cursor.fetchall()]

    # Attach options for MC questions
    mc_ids = [r["question_id"] for r in rows if r["type"] == "multiple_choice"]
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
            r["options"] = opts_by_q.get(r["question_id"], []) if r["type"] == "multiple_choice" else []
    else:
        for r in rows:
            r["options"] = []

    for r in rows:
        r["reason_label"] = REASON_LABELS.get(r["reason_type"], r["reason_type"])

    return rows


@router.post("/flags/{flag_id}/override")
async def override_flag(flag_id: int, body: OverrideBody, db=Depends(get_db)):
    if body.action not in ("remove", "keep"):
        raise HTTPException(status_code=422, detail="action must be 'remove' or 'keep'")

    flag = await (await db.execute(
        "SELECT id, question_id FROM flags WHERE id = ?", (flag_id,)
    )).fetchone()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    if body.action == "remove":
        await db.execute("DELETE FROM questions WHERE id = ?", (flag["question_id"],))
    else:
        await db.execute(
            "UPDATE flags SET verdict = 'dismissed' WHERE id = ?", (flag_id,)
        )
    await db.commit()
    return {"status": "ok"}
