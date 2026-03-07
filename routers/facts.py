from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from database import get_db
from models import FactUpdate

router = APIRouter(prefix="/api/facts", tags=["facts"])


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
    cursor = await db.execute(f"""
        SELECT f.id, f.topic_id, f.course_id, f.content, f.created_at, f.updated_at,
               c.name AS course_name
        FROM facts f
        LEFT JOIN courses c ON c.id = f.course_id
        {where}
        ORDER BY f.id
    """, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.put("/{fact_id}")
async def update_fact(fact_id: int, body: FactUpdate, db=Depends(get_db)):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Content cannot be empty")
    cursor = await db.execute(
        "UPDATE facts SET content = ?, course_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content, body.course_id, fact_id)
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fact not found")
    row = await (await db.execute("""
        SELECT f.id, f.topic_id, f.course_id, f.content, f.created_at, f.updated_at,
               c.name AS course_name
        FROM facts f
        LEFT JOIN courses c ON c.id = f.course_id
        WHERE f.id = ?
    """, (fact_id,))).fetchone()
    return dict(row)


@router.delete("/{fact_id}", status_code=204)
async def delete_fact(fact_id: int, db=Depends(get_db)):
    cursor = await db.execute(
        "DELETE FROM facts WHERE id = ?", (fact_id,)
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fact not found")
