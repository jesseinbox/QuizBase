"""Auto-resolve flags that have been sitting for more than 7 days with no user action."""

EXPIRY_DAYS = 7


async def auto_resolve_expired_flags(db) -> None:
    cursor = await db.execute("""
        SELECT id, question_id, verdict FROM flags
        WHERE datetime(created_at, '+7 days') <= datetime('now')
        AND verdict IN ('pending', 'dismissed')
    """)
    expired = [dict(r) for r in await cursor.fetchall()]
    if not expired:
        return

    for flag in expired:
        if flag["verdict"] == "dismissed":
            # AI said keep and user didn't override → accept AI decision, clean up flag
            await db.execute("DELETE FROM flags WHERE id = ?", (flag["id"],))
        elif flag["verdict"] == "pending":
            # AI review never completed → safe default is removal
            await db.execute("DELETE FROM questions WHERE id = ?", (flag["question_id"],))
            # flag cascades via ON DELETE CASCADE

    await db.commit()
