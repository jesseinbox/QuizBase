from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db
from services.question_verify import verify_and_reprocess

router = APIRouter(prefix="/api/questions", tags=["flags"])

VALID_REASONS = {"wrong_answer", "not_related", "no_sense", "other"}


class FlagCreate(BaseModel):
    reason_type: str
    reason_text: Optional[str] = None


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
