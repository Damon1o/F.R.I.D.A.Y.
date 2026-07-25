CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS events (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title      TEXT    NOT NULL,
    start_at   TEXT    NOT NULL,
    end_at     TEXT,
    all_day    INTEGER NOT NULL DEFAULT 0,
    location   TEXT,
    notes      TEXT,
    created_at TEXT    NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS todos (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title        TEXT    NOT NULL,
    due_at       TEXT,
    done         INTEGER NOT NULL DEFAULT 0,
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS'),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS messages (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role         TEXT NOT NULL,
    content      TEXT,
    tool_calls   TEXT,
    tool_call_id TEXT,
    name         TEXT,
    created_at   TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);
