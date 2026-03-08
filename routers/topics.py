from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from database import get_db
from models import TopicCreate, FactCreate
from services.question_gen import generate_and_store
from services.fact_check import check_and_flag_fact

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("")
async def list_topics(db=Depends(get_db)):
    cursor = await db.execute("""
        SELECT t.id, t.name, t.created_at,
               COUNT(f.id) AS fact_count
        FROM topics t
        LEFT JOIN facts f ON f.topic_id = t.id
        GROUP BY t.id
        ORDER BY t.name
    """)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_topic(body: TopicCreate, db=Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    try:
        cursor = await db.execute(
            "INSERT INTO topics (name) VALUES (?)", (name,)
        )
        await db.commit()
        row = await (await db.execute(
            "SELECT id, name, created_at FROM topics WHERE id = ?",
            (cursor.lastrowid,)
        )).fetchone()
        return dict(row)
    except Exception:
        raise HTTPException(status_code=409, detail="Topic name already exists")


@router.delete("/{topic_id}", status_code=204)
async def delete_topic(topic_id: int, db=Depends(get_db)):
    cursor = await db.execute(
        "DELETE FROM topics WHERE id = ?", (topic_id,)
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Topic not found")


@router.get("/{topic_id}/facts")
async def list_facts(topic_id: int, db=Depends(get_db)):
    row = await (await db.execute(
        "SELECT id FROM topics WHERE id = ?", (topic_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Topic not found")
    cursor = await db.execute("""
        SELECT f.id, f.topic_id, f.course_id, f.content, f.created_at, f.updated_at,
               f.accuracy_flag, c.name AS course_name
        FROM facts f
        LEFT JOIN courses c ON c.id = f.course_id
        WHERE f.topic_id = ?
        ORDER BY f.id
    """, (topic_id,))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("/{topic_id}/facts", status_code=201)
async def create_fact(topic_id: int, body: FactCreate, background_tasks: BackgroundTasks, db=Depends(get_db)):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Content cannot be empty")
    row = await (await db.execute(
        "SELECT id FROM topics WHERE id = ?", (topic_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Topic not found")
    cursor = await db.execute(
        "INSERT INTO facts (topic_id, course_id, content) VALUES (?, ?, ?)",
        (topic_id, body.course_id, content)
    )
    await db.commit()
    fact_id = cursor.lastrowid
    row = await (await db.execute("""
        SELECT f.id, f.topic_id, f.course_id, f.content, f.created_at, f.updated_at,
               f.accuracy_flag, c.name AS course_name
        FROM facts f
        LEFT JOIN courses c ON c.id = f.course_id
        WHERE f.id = ?
    """, (fact_id,))).fetchone()
    fact = dict(row)
    background_tasks.add_task(generate_and_store, fact_id, fact["content"])
    background_tasks.add_task(check_and_flag_fact, fact_id, fact["content"])
    return fact
