from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from database import get_db
from models import FactUpdate
from services.fact_check import check_and_flag_fact

router = APIRouter(prefix="/api/facts", tags=["facts"])

FACT_SELECT = """
    SELECT f.id, f.topic_id, f.course_id, f.content, f.created_at, f.updated_at,
           f.accuracy_flag, c.name AS course_name
    FROM facts f
    LEFT JOIN courses c ON c.id = f.course_id
"""


@router.get("")
async def list_all_facts(
    topic_id: Optional[int] = Query(None),
    course_id: Optional[int] = Query(None),
    db=Depends(get_db),
):
    conditions = []
    params = []
    if topic_id is not None:
        conditions.append("f.topic_id = ?")
        params.append(topic_id)
    if course_id is not None:
        conditions.append("f.course_id = ?")
        params.append(course_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cursor = await db.execute(f"{FACT_SELECT} {where} ORDER BY f.id", params)
    return [dict(r) for r in await cursor.fetchall()]


@router.get("/flagged")
async def list_flagged_facts(db=Depends(get_db)):
    cursor = await db.execute(f"""
        {FACT_SELECT}
        JOIN topics t ON t.id = f.topic_id
        WHERE f.accuracy_flag IS NOT NULL
        ORDER BY f.topic_id, f.id
    """)
    rows = [dict(r) for r in await cursor.fetchall()]
    # Attach topic name
    topic_cursor = await db.execute("SELECT id, name FROM topics")
    topics = {r["id"]: r["name"] for r in await topic_cursor.fetchall()}
    for r in rows:
        r["topic_name"] = topics.get(r["topic_id"], "")
    return rows


@router.put("/{fact_id}")
async def update_fact(
    fact_id: int,
    body: FactUpdate,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Content cannot be empty")
    cursor = await db.execute(
        "UPDATE facts SET content = ?, course_id = ?, accuracy_flag = NULL, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content, body.course_id, fact_id),
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fact not found")
    row = await (await db.execute(f"{FACT_SELECT} WHERE f.id = ?", (fact_id,))).fetchone()
    fact = dict(row)
    background_tasks.add_task(check_and_flag_fact, fact_id, content)
    return fact


@router.post("/{fact_id}/dismiss-flag", status_code=204)
async def dismiss_flag(fact_id: int, db=Depends(get_db)):
    cursor = await db.execute(
        "UPDATE facts SET accuracy_flag = NULL WHERE id = ?", (fact_id,)
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fact not found")


@router.delete("/{fact_id}", status_code=204)
async def delete_fact(fact_id: int, db=Depends(get_db)):
    cursor = await db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fact not found")
