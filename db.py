"""
Database layer for ReadFlow AI.

Responsibilities:
  - Manage per-request SQLite connections (via Flask's g object).
  - Define and migrate the schema on startup.
  - Provide thin query helpers used across blueprints.
  - Compute analytics (reading streak).
"""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from flask import current_app, g


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys  = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER,
    title             TEXT,
    original_filename TEXT,
    stored_filename   TEXT,
    file_type         TEXT,
    source_type       TEXT      NOT NULL DEFAULT 'manual',
    content           TEXT,
    word_count        INTEGER   NOT NULL DEFAULT 0,
    last_position     INTEGER   NOT NULL DEFAULT 0,
    last_wpm          INTEGER   NOT NULL DEFAULT 200,
    last_mode         TEXT      NOT NULL DEFAULT 'word',
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_documents_user_updated
    ON documents (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS reading_sessions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               INTEGER NOT NULL,
    document_id           INTEGER NOT NULL,
    document_name         TEXT    NOT NULL,
    started_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at              TIMESTAMP,
    duration_seconds      INTEGER NOT NULL DEFAULT 0,
    wpm                   INTEGER NOT NULL DEFAULT 200,
    reading_mode          TEXT    NOT NULL DEFAULT 'word',
    completion_percentage INTEGER NOT NULL DEFAULT 0,
    words_read            INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_started
    ON reading_sessions (user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_doc
    ON reading_sessions (user_id, document_id, started_at DESC);

CREATE TABLE IF NOT EXISTS bookmarks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    label       TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_doc ON bookmarks (user_id, document_id);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    body        TEXT    NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notes_doc ON notes (user_id, document_id);

CREATE TABLE IF NOT EXISTS highlights (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    document_id    INTEGER NOT NULL,
    start_position INTEGER NOT NULL DEFAULT 0,
    end_position   INTEGER NOT NULL DEFAULT 0,
    text           TEXT    NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_highlights_doc ON highlights (user_id, document_id);

CREATE TABLE IF NOT EXISTS settings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL UNIQUE,
    default_wpm          INTEGER NOT NULL DEFAULT 200,
    default_mode         TEXT    NOT NULL DEFAULT 'word',
    smart_pause_enabled  INTEGER NOT NULL DEFAULT 1,
    theme                TEXT    NOT NULL DEFAULT 'dark',
    font_size            INTEGER NOT NULL DEFAULT 100,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- FTS5 virtual tables mirror documents and notes for fast full-text search.
-- The triggers below keep them in sync with source tables automatically.
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
    USING fts5(title, content, content='documents', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS documents_fts_insert AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, content)
        VALUES (new.id, COALESCE(new.title, ''), COALESCE(new.content, ''));
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_update AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
        VALUES ('delete', old.id, COALESCE(old.title, ''), COALESCE(old.content, ''));
    INSERT INTO documents_fts(rowid, title, content)
        VALUES (new.id, COALESCE(new.title, ''), COALESCE(new.content, ''));
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_delete AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
        VALUES ('delete', old.id, COALESCE(old.title, ''), COALESCE(old.content, ''));
END;

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
    USING fts5(body, content='notes', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, COALESCE(new.body, ''));
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body)
        VALUES ('delete', old.id, COALESCE(old.body, ''));
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, COALESCE(new.body, ''));
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body)
        VALUES ('delete', old.id, COALESCE(old.body, ''));
END;
"""

# Columns added post-launch; maps table → {column_name: DDL snippet}
_MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "documents": {
        "user_id":       "INTEGER",
        "title":         "TEXT",
        "content":       "TEXT",
        "last_position": "INTEGER NOT NULL DEFAULT 0",
        "last_wpm":      "INTEGER NOT NULL DEFAULT 200",
        "last_mode":     "TEXT    NOT NULL DEFAULT 'word'",
        "updated_at":    "TIMESTAMP",
    }
}


# ── Connection management ─────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return the per-request SQLite connection, opening it on first access."""
    if "db" not in g:
        g.db = sqlite3.connect(
            str(current_app.config["DATABASE_PATH"]),
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(_error=None) -> None:
    """App teardown callback — close the connection at end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction():
    """Yield the active connection; commit on clean exit, rollback on error."""
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Initialisation ────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create schema, run column migrations, and populate FTS indexes."""
    current_app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    with transaction() as db:
        db.executescript(SCHEMA)
        _run_migrations(db)
        _rebuild_fts_if_needed(db)


def _run_migrations(db: sqlite3.Connection) -> None:
    """Add any missing columns to existing tables (non-destructive)."""
    for table, columns in _MIGRATION_COLUMNS.items():
        existing = {
            row["name"]
            for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for col_name, col_def in columns.items():
            if col_name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


def _rebuild_fts_if_needed(db: sqlite3.Connection) -> None:
    """
    Backfill FTS indexes for databases that pre-date FTS support.

    FTS5 'rebuild' repopulates the index from the content= source table;
    we only run it once — when the FTS table is empty but the source is not.
    """
    try:
        fts_doc = db.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]
        src_doc = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if src_doc > 0 and fts_doc == 0:
            db.execute("INSERT INTO documents_fts(documents_fts) VALUES ('rebuild')")

        fts_note = db.execute("SELECT COUNT(*) FROM notes_fts").fetchone()[0]
        src_note = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        if src_note > 0 and fts_note == 0:
            db.execute("INSERT INTO notes_fts(notes_fts) VALUES ('rebuild')")
    except Exception:
        pass  # FTS absent on very old schemas — ignore silently


# ── Query helpers ─────────────────────────────────────────────────────────────

def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """Execute *sql* and return the first row, or None."""
    return get_db().execute(sql, params).fetchone()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Execute *sql* and return all rows."""
    return get_db().execute(sql, params).fetchall()


# ── Default user (no-auth mode) ───────────────────────────────────────────────

_DEFAULT_USER_EMAIL = "__default__@readflow.local"


def get_or_create_default_user() -> sqlite3.Row:
    """
    Return the user to auto-login as when no session exists.

    Strategy:
      1. If any real (non-placeholder) user exists, use the first one — this
         preserves existing data on a personal install.
      2. Otherwise create the built-in placeholder and use that.
    """
    # Pick the user with the most recent reading or document activity.
    # Falls back to the most recently created user (highest id) if no activity.
    real_user = query_one(
        """
        SELECT u.*
        FROM   users u
        LEFT JOIN documents d ON d.user_id = u.id
        WHERE  u.email != ?
        GROUP  BY u.id
        ORDER  BY MAX(d.updated_at) DESC NULLS LAST, u.id DESC
        LIMIT  1
        """,
        (_DEFAULT_USER_EMAIL,),
    )
    if real_user:
        return real_user

    # No real user yet — create the built-in default
    placeholder = query_one("SELECT * FROM users WHERE email = ?", (_DEFAULT_USER_EMAIL,))
    if placeholder:
        return placeholder

    with transaction() as db:
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Reader", _DEFAULT_USER_EMAIL, "disabled"),
        )
        user_id = cursor.lastrowid
        db.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


# ── Settings helper ───────────────────────────────────────────────────────────

def get_or_create_user_settings(user_id: int) -> sqlite3.Row:
    """Return the user's settings row, inserting defaults if absent."""
    row = query_one("SELECT * FROM settings WHERE user_id = ?", (user_id,))
    if row is None:
        with transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,)
            )
        row = query_one("SELECT * FROM settings WHERE user_id = ?", (user_id,))
    return row


# ── Reading session helper ────────────────────────────────────────────────────

def get_or_create_reading_session(
    document: sqlite3.Row, user_settings: sqlite3.Row, user_id: int
) -> int:
    """
    Return an existing open session id if one was started within the last
    5 minutes for this document (avoids history inflation on page refresh),
    otherwise create a new session row.
    """
    recent = query_one(
        """
        SELECT id FROM reading_sessions
        WHERE  user_id     = ?
          AND  document_id = ?
          AND  ended_at    IS NULL
          AND  started_at  > datetime('now', '-5 minutes')
        ORDER  BY started_at DESC
        LIMIT  1
        """,
        (user_id, document["id"]),
    )
    if recent:
        return recent["id"]

    completion = int(
        (document["last_position"] / max(document["word_count"], 1)) * 100
    )
    with transaction() as db:
        cursor = db.execute(
            """
            INSERT INTO reading_sessions
                (user_id, document_id, document_name,
                 wpm, reading_mode, completion_percentage, words_read)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                document["id"],
                document["title"],
                document["last_wpm"] or user_settings["default_wpm"],
                document["last_mode"] or user_settings["default_mode"],
                completion,
                document["last_position"],
            ),
        )
        return cursor.lastrowid


# ── Analytics ─────────────────────────────────────────────────────────────────

def reading_streak(user_id: int) -> int:
    """Return the current consecutive-days reading streak for *user_id*."""
    rows = query_all(
        """
        SELECT DATE(started_at) AS read_date
        FROM   reading_sessions
        WHERE  user_id = ? AND words_read > 0
        GROUP  BY DATE(started_at)
        ORDER  BY read_date DESC
        """,
        (user_id,),
    )
    days = {
        datetime.strptime(row["read_date"], "%Y-%m-%d").date()
        for row in rows
        if row["read_date"]
    }
    streak, cursor = 0, date.today()
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
