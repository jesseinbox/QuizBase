import aiosqlite

DB_PATH = "quizbase.db"

CREATE_COURSES = """
CREATE TABLE IF NOT EXISTS courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_TOPICS = """
CREATE TABLE IF NOT EXISTS topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_FACTS = """
CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id   INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    course_id  INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    content    TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_QUESTIONS = """
CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id    INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    statement  TEXT NOT NULL,
    is_true    INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


CREATE_QUESTION_OPTIONS = """
CREATE TABLE IF NOT EXISTS question_options (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    is_correct  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0
)
"""

CREATE_PROGRESS = """
CREATE TABLE IF NOT EXISTS question_progress (
    question_id     INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
    correct_count   INTEGER NOT NULL DEFAULT 0,
    next_due_at     TEXT,
    last_answered_at TEXT,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_FLAGS = """
CREATE TABLE IF NOT EXISTS flags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    reason_type TEXT NOT NULL,
    reason_text TEXT,
    verdict     TEXT DEFAULT 'pending',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(CREATE_COURSES)
        await db.execute(CREATE_TOPICS)
        await db.execute(CREATE_FACTS)
        await db.execute(CREATE_QUESTIONS)
        await db.execute(CREATE_QUESTION_OPTIONS)
        await db.execute(CREATE_PROGRESS)
        # Add 'type' column to existing questions tables (no-op if already present)
        try:
            await db.execute(
                "ALTER TABLE questions ADD COLUMN type TEXT NOT NULL DEFAULT 'true_false'"
            )
        except Exception:
            pass
        # Add verdict_explanation to flags (no-op if already present)
        try:
            await db.execute("ALTER TABLE flags ADD COLUMN verdict_explanation TEXT")
        except Exception:
            pass
        # Add grading_notes to questions for short-answer type (no-op if already present)
        try:
            await db.execute("ALTER TABLE questions ADD COLUMN grading_notes TEXT")
        except Exception:
            pass
        await db.execute(CREATE_FLAGS)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
