import sqlite3
from pathlib import Path

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 로컬 개발용 DB (GitHub 업로드 제외)
DB_PATH = PROJECT_ROOT / "data" / "local" / "backend_b.db"


def get_connection():
    """SQLite 데이터베이스 연결"""
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    """자동화 작업 및 감사 이벤트 테이블 생성"""
    with get_connection() as connection:

        # 1. 자동화 작업 테이블
        connection.execute("""
            CREATE TABLE IF NOT EXISTS automation_jobs (
                job_id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                cycle_no INTEGER NOT NULL,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT NOT NULL,
                lease_token TEXT,
                lease_until TEXT,
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                UNIQUE(ticket_id, cycle_no)
            )
        """)

        # 2. 감사 이벤트 테이블
        connection.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                ticket_id TEXT,
                cycle_no INTEGER,
                actor_user_id TEXT,
                actor_service TEXT,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                event_key TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


if __name__ == "__main__":
    init_db()
    print(f"SQLite DB initialized: {DB_PATH}")
