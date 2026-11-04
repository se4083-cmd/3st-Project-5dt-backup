-- Development-only SQLite store. Every record is synthetic.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS runtime_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  epoch INTEGER NOT NULL CHECK (epoch >= 1),
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS command_receipts (
  scope TEXT NOT NULL,
  request_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  epoch INTEGER NOT NULL,
  applied_revision INTEGER NOT NULL,
  receipt_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (scope, request_id)
);
CREATE TABLE IF NOT EXISTS runtime_events (
  epoch INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  ticket_id TEXT,
  cycle INTEGER,
  event_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (epoch, event_id)
);
CREATE TABLE IF NOT EXISTS final_replies (
  epoch INTEGER NOT NULL,
  ticket_id TEXT NOT NULL,
  cycle INTEGER NOT NULL,
  message_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  author TEXT NOT NULL CHECK (author IN ('SYSTEM','AGENT')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (epoch, ticket_id, cycle),
  UNIQUE (epoch, message_id)
);
CREATE TABLE IF NOT EXISTS demo_orders (
  id TEXT PRIMARY KEY,
  customer_ref TEXT NOT NULL,
  status TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  eta TEXT
);
