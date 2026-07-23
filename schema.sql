CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    start_at   TEXT    NOT NULL,           -- ISO-8601
    end_at     TEXT,                       -- ISO-8601, nullable
    all_day    INTEGER NOT NULL DEFAULT 0, -- 0/1 boolean
    location   TEXT,
    notes      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    due_at       TEXT,                       -- ISO-8601, nullable
    done         INTEGER NOT NULL DEFAULT 0, -- 0/1 boolean
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT                        -- set when done flips to 1
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    role         TEXT NOT NULL,              -- user | assistant | tool
    content      TEXT,                       -- text, or tool-result JSON for role=tool
    tool_calls   TEXT,                       -- JSON array when assistant requests tools
    tool_call_id TEXT,                       -- role=tool: which call it answers
    name         TEXT,                       -- role=tool: tool name
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
