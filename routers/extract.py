from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from database import get_db
from services.fact_extract import extract_facts, extract_pdf_text
from services.question_gen import generate_and_store

router = APIRouter(prefix="/api/extract", tags=["extract"])

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/pdf")
async def extract_from_pdf(
    file: UploadFile = File(...),
    max_facts: int = Form(10),
    focus: str = Form("general"),
    depth: str = Form("easy"),
    start_page: int = Form(1),
    end_page: int = Form(20),
    avoid_duplicates: bool = Form(False),
    topic_id: Optional[int] = Form(None),
    db=Depends(get_db),
):
    if end_page - start_page + 1 > 100:
        raise HTTPException(status_code=400, detail="Page range exceeds 100 pages. Please upload a smaller file or narrow your page range.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (20 MB max).")

    try:
        text, pages_processed, total_pages = extract_pdf_text(content, start_page, end_page)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read PDF: {exc}")

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No text found in the PDF. The file may be image-based or encrypted.",
        )

    existing_facts: list[str] = []
    if avoid_duplicates and topic_id:
        cursor = await db.execute("SELECT content FROM facts WHERE topic_id = ?", (topic_id,))
        existing_facts = [row[0] for row in await cursor.fetchall()]

    try:
        facts = await extract_facts(text, max_facts, focus, depth, existing_facts or None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")

    return {
        "facts": facts,
        "pages_processed": pages_processed,
        "total_pages": total_pages,
        "char_count": len(text),
    }


class ImportBody(BaseModel):
    topic_id: int
    course_id: Optional[int] = None
    facts: list[str]


@router.post("/import")
async def import_facts(
    body: ImportBody,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    if not body.facts:
        raise HTTPException(status_code=400, detail="No facts provided.")

    topic = await (await db.execute(
        "SELECT id FROM topics WHERE id = ?", (body.topic_id,)
    )).fetchone()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    added = 0
    for content in body.facts:
        content = content.strip()
        if not content:
            continue
        cursor = await db.execute(
            "INSERT INTO facts (topic_id, course_id, content) VALUES (?, ?, ?)",
            (body.topic_id, body.course_id or None, content),
        )
        fact_id = cursor.lastrowid
        background_tasks.add_task(generate_and_store, fact_id, content)
        added += 1

    await db.commit()
    return {"added": added}
