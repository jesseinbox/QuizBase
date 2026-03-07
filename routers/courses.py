from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from models import CourseCreate

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("")
async def list_courses(db=Depends(get_db)):
    cursor = await db.execute("""
        SELECT id, name, created_at
        FROM courses
        ORDER BY name
    """)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_course(body: CourseCreate, db=Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    try:
        cursor = await db.execute(
            "INSERT INTO courses (name) VALUES (?)", (name,)
        )
        await db.commit()
        row = await (await db.execute(
            "SELECT id, name, created_at FROM courses WHERE id = ?",
            (cursor.lastrowid,)
        )).fetchone()
        return dict(row)
    except Exception:
        raise HTTPException(status_code=409, detail="Course name already exists")


@router.delete("/{course_id}", status_code=204)
async def delete_course(course_id: int, db=Depends(get_db)):
    cursor = await db.execute(
        "DELETE FROM courses WHERE id = ?", (course_id,)
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Course not found")
