"""One-shot script: generate questions for all facts that have none."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from services.question_gen import generate_and_store
import aiosqlite
from database import DB_PATH


async def main():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT f.id, f.content FROM facts f
            LEFT JOIN questions q ON q.fact_id = f.id
            WHERE q.id IS NULL
            GROUP BY f.id
        """)
        facts = [dict(r) for r in await cursor.fetchall()]

    if not facts:
        print("Nothing to backfill.")
        return

    print(f"Generating questions for {len(facts)} fact(s)…")
    for fact in facts:
        print(f"  [{fact['id']}] {fact['content'][:70]}")
        await generate_and_store(fact["id"], fact["content"])
        print(f"       done")

    print("Backfill complete.")


asyncio.run(main())
