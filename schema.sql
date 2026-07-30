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

-- Spec R: single tag per todo (Option A). Spec L: recurrence rule + skipped dates.
ALTER TABLE todos  ADD COLUMN IF NOT EXISTS tag     TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS rrule   TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS exdates TEXT;

-- Spec S: append-only undo log. One row per mutation; undo() pops the latest for the session.
CREATE TABLE IF NOT EXISTS undo_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id   TEXT NOT NULL DEFAULT 'default',
    op           TEXT NOT NULL,
    target_table TEXT NOT NULL,
    row_id       BIGINT,
    payload      TEXT,
    created_at   TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

-- Migration runs BEFORE the index: on a pre-session_id table the index would
-- reference a column that does not exist yet and abort the whole schema run.
-- Migration: replace legacy single-row undo_log (id=1 CHECK) with append-only version.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'undo_log' AND constraint_name = 'undo_log_id_check'
    ) THEN
        -- Drop the old constraint and table, recreate properly
        DROP TABLE undo_log;
        CREATE TABLE undo_log (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            session_id   TEXT NOT NULL DEFAULT 'default',
            op           TEXT NOT NULL,
            target_table TEXT NOT NULL,
            row_id       BIGINT,
            payload      TEXT,
            created_at   TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
        );
        CREATE INDEX undo_log_session_id_idx ON undo_log (session_id, id DESC);
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns WHERE table_name='undo_log' AND column_name='session_id'
    ) THEN
        -- Has new table but missing session_id column
        ALTER TABLE undo_log ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default';
        CREATE INDEX IF NOT EXISTS undo_log_session_id_idx ON undo_log (session_id, id DESC);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS undo_log_session_id_idx ON undo_log (session_id, id DESC);

-- Indexes for the queries the app actually runs: date-window event lookups,
-- open/overdue task filters, and newest-first note/message paging.
CREATE INDEX IF NOT EXISTS events_start_at_idx  ON events   (start_at);
CREATE INDEX IF NOT EXISTS todos_done_due_idx   ON todos    (done, due_at);
CREATE INDEX IF NOT EXISTS todos_completed_idx  ON todos    (completed_at);
CREATE INDEX IF NOT EXISTS todos_tag_idx        ON todos    (tag);
CREATE INDEX IF NOT EXISTS notes_created_at_idx ON notes    (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS messages_id_idx      ON messages (id DESC);

-- Conversations: every message belongs to a thread, so "new chat" starts thread N+1
-- instead of deleting history. Existing rows collapse into thread 1.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS thread_id BIGINT NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS messages_thread_idx ON messages (thread_id, id DESC);

-- ============================================================================
-- Infinite Campus grades (Spec: docs/superpowers/specs/2026-07-29-infinite-campus-grades-design.md)
-- Read-only mirror of the student's own portal data. Sync upserts on the Campus
-- IDs, so re-running it is idempotent.
-- ============================================================================
CREATE TABLE IF NOT EXISTS courses (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id   TEXT UNIQUE NOT NULL,   -- Campus sectionID: the sync key
    name         TEXT NOT NULL,
    teacher      TEXT,
    period       TEXT,
    term         TEXT,
    grade_pct    REAL,
    grade_letter TEXT,
    synced_at    TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS assignments (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campus_id  TEXT UNIQUE NOT NULL,
    section_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    category   TEXT,                   -- Homework / Test / Project — powers category ranking
    points     REAL,
    total      REAL,
    due_at     TEXT,
    missing    INTEGER NOT NULL DEFAULT 0,
    synced_at  TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

-- One row per *change* in a course percent, not one per sync. That is what makes
-- drop detection work without a cron job.
CREATE TABLE IF NOT EXISTS grade_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id  TEXT NOT NULL,
    grade_pct   REAL,
    recorded_at TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE INDEX IF NOT EXISTS assignments_section_idx   ON assignments   (section_id);
CREATE INDEX IF NOT EXISTS grade_history_section_idx ON grade_history (section_id, recorded_at DESC);
