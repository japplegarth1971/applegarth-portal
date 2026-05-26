import sqlite3
import pathlib
import bcrypt

DB_PATH = pathlib.Path(__file__).parent / "portal.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name          TEXT NOT NULL,
            organisation  TEXT NOT NULL,
            org_type      TEXT NOT NULL,
            phone         TEXT DEFAULT '',
            approved      INTEGER DEFAULT 0,
            is_admin      INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS assessments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id      INTEGER NOT NULL,
            title          TEXT NOT NULL,
            type           TEXT NOT NULL,
            completed_date TEXT,
            review_date    TEXT,
            notes          TEXT DEFAULT '',
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documents (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id     INTEGER NOT NULL,
            assessment_id INTEGER,
            filename      TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size     INTEGER DEFAULT 0,
            uploaded_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id)     REFERENCES users(id)        ON DELETE CASCADE,
            FOREIGN KEY (assessment_id) REFERENCES assessments(id)  ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS action_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            client_id     INTEGER NOT NULL,
            description   TEXT NOT NULL,
            status        TEXT DEFAULT 'open',
            created_at    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
            FOREIGN KEY (client_id)     REFERENCES users(id)       ON DELETE CASCADE
        );
    """)

    # Seed default admin if none exists
    admin = conn.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
    if not admin:
        pw_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        conn.execute("""
            INSERT INTO users (email, password_hash, name, organisation, org_type, approved, is_admin)
            VALUES (?, ?, ?, ?, ?, 1, 1)
        """, [
            "info@applegarthhealthandsafety.co.uk",
            pw_hash,
            "Jeremy Applegarth",
            "Applegarth Health and Safety",
            "consultant",
        ])

    conn.commit()
    conn.close()
