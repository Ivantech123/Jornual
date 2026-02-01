from __future__ import annotations

import hashlib
import hmac
import math
import os
import secrets
import socket
import sqlite3
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "journal.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("JOURNAL_SECRET", "dev-key-change-me")
app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL", "").strip()
app.config["SUPABASE_ANON_KEY"] = os.environ.get("SUPABASE_ANON_KEY", "").strip()
app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
app.config["SUPABASE_DB_URL"] = os.environ.get("SUPABASE_DB_URL", "").strip()
app.config["SUPABASE_POOLER_URL"] = os.environ.get("SUPABASE_POOLER_URL", "").strip()
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL", "").strip()
app.config["INVITE_TTL_DAYS"] = int(os.environ.get("INVITE_TTL_DAYS", "7"))
app.config["TELEGRAM_BOT_TOKEN"] = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
app.config["TELEGRAM_BOT_USERNAME"] = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip()
app.config["TELEGRAM_WEBHOOK_SECRET"] = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
app.config["TELEGRAM_TOKEN_TTL_MINUTES"] = int(os.environ.get("TELEGRAM_TOKEN_TTL_MINUTES", "15"))
app.config["TELEGRAM_LOGIN_TTL_SECONDS"] = int(os.environ.get("TELEGRAM_LOGIN_TTL_SECONDS", "600"))

ADMIN_EMAILS = {
    value.strip().lower()
    for value in os.environ.get("ADMIN_EMAILS", "").split(",")
    if value.strip()
}
ADMIN_TELEGRAM_IDS = {
    value.strip()
    for value in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    if value.strip()
}

app.config["DB_ENGINE"] = (
    "postgres"
    if app.config["SUPABASE_DB_URL"]
    or app.config["SUPABASE_POOLER_URL"]
    or app.config["DATABASE_URL"]
    else "sqlite"
)

if app.config["DB_ENGINE"] == "postgres":
    if os.environ.get("VERCEL") and app.config["SUPABASE_POOLER_URL"]:
        app.config["DATABASE"] = app.config["SUPABASE_POOLER_URL"]
    else:
        app.config["DATABASE"] = (
            app.config["SUPABASE_DB_URL"] or app.config["SUPABASE_POOLER_URL"] or app.config["DATABASE_URL"]
        )
else:
    app.config["DATABASE"] = Path(os.environ.get("JOURNAL_DB_PATH", str(DEFAULT_DB_PATH)))
    if os.environ.get("VERCEL") and "JOURNAL_DB_PATH" not in os.environ:
        app.config["DATABASE"] = Path("/tmp/journal.db")

DEFAULT_STUDENTS = [
    "Andreev",
    "Gavrikov",
    "Gordeev",
    "Grishin",
    "Emelyanova",
    "Zhukov",
    "Imomdodov",
    "Iskanderova",
    "Kozirev",
    "Krasnobaev",
    "Maslova",
    "Osipov",
    "Polozova",
    "Pryahin",
    "Razzhivin",
    "Romanova",
    "Ryabkov",
    "Snegur",
    "Tihomirov",
    "Tkachenko",
    "Trubitsa",
    "Haliev",
    "Sheshin",
    "Sherbaev",
]

SCHEMA_READY = False


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def is_postgres() -> bool:
    return app.config.get("DB_ENGINE") == "postgres"


def adapt_sql(sql: str) -> str:
    return sql.replace("?", "%s") if is_postgres() else sql


def sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def ensure_sqlite_columns(
    conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]]
) -> None:
    existing = sqlite_columns(conn, table)
    for name, column_type in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def configure_connection(conn: sqlite3.Connection) -> None:
    if is_postgres():
        return
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 3000")


def connect_postgres():
    import psycopg

    dsn = app.config["DATABASE"]
    if not dsn:
        raise RuntimeError("DATABASE URL is not configured.")

    kwargs: Dict[str, Any] = {}
    if "sslmode=" not in dsn:
        kwargs["sslmode"] = "require"

    try:
        parsed = urlparse(dsn)
        host = parsed.hostname
        port = parsed.port or 5432
        if host:
            try:
                info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
                if info:
                    kwargs["hostaddr"] = info[0][4][0]
            except OSError:
                pass
    except Exception:
        pass

    return psycopg.connect(dsn, **kwargs)


def ensure_schema() -> None:
    if is_postgres():
        conn = connect_postgres()
        schema_sql = """
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            student_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            grade REAL NOT NULL,
            date TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_grades_student_date
            ON grades(student_id, date);

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            student_id TEXT NOT NULL,
            date TEXT NOT NULL,
            present INTEGER NOT NULL CHECK(present IN (0, 1)),
            note TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_attendance_student_date
            ON attendance(student_id, date);

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            student_id TEXT,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );

        ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_username TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_verified_at TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS student_id TEXT;

        CREATE INDEX IF NOT EXISTS idx_users_role
            ON users(role);

        CREATE TABLE IF NOT EXISTS admin_invites (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            used_by TEXT,
            used_at TEXT
        );

        CREATE TABLE IF NOT EXISTS telegram_links (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            telegram_id TEXT,
            telegram_username TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_telegram_links_user
            ON telegram_links(user_id);

        CREATE INDEX IF NOT EXISTS idx_telegram_links_expires
            ON telegram_links(expires_at);
        """
        with conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
        conn.close()
        return

    db_path: Path = app.config["DATABASE"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    configure_connection(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            grade REAL NOT NULL,
            date TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_grades_student_date
            ON grades(student_id, date);

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date TEXT NOT NULL,
            present INTEGER NOT NULL CHECK(present IN (0, 1)),
            note TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_attendance_student_date
            ON attendance(student_id, date);

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            student_id TEXT,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_users_role
            ON users(role);

        CREATE TABLE IF NOT EXISTS admin_invites (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            used_by TEXT,
            used_at TEXT
        );

        CREATE TABLE IF NOT EXISTS telegram_links (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            telegram_id TEXT,
            telegram_username TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_telegram_links_user
            ON telegram_links(user_id);

        CREATE INDEX IF NOT EXISTS idx_telegram_links_expires
            ON telegram_links(expires_at);
        """
    )
    ensure_sqlite_columns(
        conn,
        "users",
        [
            ("telegram_id", "TEXT"),
            ("telegram_username", "TEXT"),
            ("telegram_verified_at", "TEXT"),
            ("student_id", "TEXT"),
        ],
    )
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        if is_postgres():
            from psycopg.rows import dict_row

            conn = connect_postgres()
            conn.autocommit = False
            g.db = conn
            g.db_row_factory = dict_row
        else:
            db = sqlite3.connect(app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
            db.row_factory = sqlite3.Row
            configure_connection(db)
            g.db = db
    return g.db


def db_fetchall(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = get_db()
    sql = adapt_sql(sql)
    if is_postgres():
        row_factory = g.get("db_row_factory")
        with conn.cursor(row_factory=row_factory) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(row) for row in rows]
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def db_fetchone(sql: str, params: tuple = ()) -> Dict[str, Any] | None:
    conn = get_db()
    sql = adapt_sql(sql)
    if is_postgres():
        row_factory = g.get("db_row_factory")
        with conn.cursor(row_factory=row_factory) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row) if row else None
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def db_execute(sql: str, params: tuple = ()) -> None:
    conn = get_db()
    sql = adapt_sql(sql)
    if is_postgres():
        with conn.cursor() as cur:
            cur.execute(sql, params)
    else:
        conn.execute(sql, params)
    conn.commit()


def db_executemany(sql: str, params: list[tuple]) -> None:
    conn = get_db()
    sql = adapt_sql(sql)
    if is_postgres():
        with conn.cursor() as cur:
            cur.executemany(sql, params)
    else:
        conn.executemany(sql, params)
    conn.commit()


@app.teardown_appcontext
def close_db(exception: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def init_schema_once() -> None:
    global SCHEMA_READY
    if SCHEMA_READY:
        return
    ensure_schema()
    seed_students_if_empty()
    SCHEMA_READY = True


def fetch_supabase_user(access_token: str) -> Dict[str, Any] | None:
    supabase_url = app.config["SUPABASE_URL"]
    supabase_key = app.config["SUPABASE_ANON_KEY"]
    if not supabase_url or not supabase_key or not access_token:
        return None
    url = f"{supabase_url.rstrip('/')}/auth/v1/user"
    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": supabase_key,
            },
            timeout=6,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def create_supabase_user(email: str, password: str) -> tuple[bool, str]:
    supabase_url = app.config["SUPABASE_URL"]
    service_key = app.config["SUPABASE_SERVICE_ROLE_KEY"]
    if not supabase_url or not service_key:
        return False, "admin_signup_disabled"
    url = f"{supabase_url.rstrip('/')}/auth/v1/admin/users"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
            },
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
            },
            timeout=8,
        )
    except requests.RequestException:
        return False, "network"
    if response.status_code in {200, 201}:
        return True, "ok"
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = str(payload.get("msg") or payload.get("error") or "").lower()
    if "already" in error or "exists" in error or "registered" in error:
        return False, "user_exists"
    return False, "failed"


def normalize_role(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    if value in {"student", "teacher"}:
        return value
    return None


def normalize_student_id(value: str | None) -> str | None:
    value = (value or "").strip()
    return value if value else None


def upsert_user(
    user_id: str,
    email: str,
    requested_role: str | None = None,
    requested_student_id: str | None = None,
) -> Dict[str, Any]:
    now = now_iso()
    email_lower = email.lower()
    requested_role = normalize_role(requested_role)
    requested_student_id = normalize_student_id(requested_student_id)
    row = db_fetchone(
        "SELECT role, telegram_verified_at, student_id FROM users WHERE id = ?",
        (user_id,),
    )
    if row:
        role = row["role"]
        student_id = row.get("student_id")
        telegram_verified_at = row.get("telegram_verified_at")
        if email_lower in ADMIN_EMAILS and role != "admin":
            role = "admin"
        updates = ["email = ?", "last_seen = ?"]
        params: list[Any] = [email, now]
        if role != row["role"]:
            updates.append("role = ?")
            params.append(role)
        if requested_role == "student" and not student_id and requested_student_id:
            updates.append("student_id = ?")
            params.append(requested_student_id)
            student_id = requested_student_id
        params.append(user_id)
        db_execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(params))
    else:
        if email_lower in ADMIN_EMAILS:
            role = "admin"
        elif requested_role:
            role = requested_role
        else:
            role = "teacher"
        telegram_verified_at = None
        student_id = requested_student_id if role == "student" else None
        db_execute(
            "INSERT INTO users (id, email, role, student_id, created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email, role, student_id, now, now),
        )
    return {
        "role": role,
        "telegram_verified": bool(telegram_verified_at),
        "student_id": student_id,
    }


def list_users() -> List[Dict[str, Any]]:
    return db_fetchall(
        "SELECT id, email, role, created_at, last_seen FROM users ORDER BY created_at DESC"
    )


def list_invites() -> List[Dict[str, Any]]:
    return db_fetchall(
        """
        SELECT token, created_at, expires_at, used_by, used_at
        FROM admin_invites
        ORDER BY created_at DESC
        """
    )


def create_invite() -> str:
    token = secrets.token_urlsafe(24)
    now = now_iso()
    ttl_days = app.config.get("INVITE_TTL_DAYS", 7)
    expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).replace(microsecond=0).isoformat() + "Z"
    db_execute(
        "INSERT INTO admin_invites (token, created_at, expires_at) VALUES (?, ?, ?)",
        (token, now, expires_at),
    )
    return token


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        hydrate_session_user()
        return view(*args, **kwargs)

    return wrapper


def telegram_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("telegram_verified"):
            return redirect(url_for("telegram_link"))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        hydrate_session_user()
        if not session.get("telegram_verified"):
            return redirect(url_for("telegram_link"))
        if session.get("role") == "student":
            return redirect(url_for("student_portal"))
        if session.get("role") != "admin":
            return redirect(url_for("pending"))
        return view(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_globals() -> Dict[str, Any]:
    return {
        "current_user": {
            "email": session.get("email"),
            "role": session.get("role"),
        }
        if session.get("user_id")
        else None,
        "is_admin": session.get("role") == "admin",
        "telegram_enabled": telegram_enabled(),
        "telegram_login_enabled": telegram_login_enabled(),
        "telegram_verified": session.get("telegram_verified"),
        "telegram_bot_username": app.config["TELEGRAM_BOT_USERNAME"].strip().lstrip("@"),
        "supabase_url": app.config["SUPABASE_URL"],
        "supabase_anon_key": app.config["SUPABASE_ANON_KEY"],
    }


def seed_students_if_empty() -> None:
    row = db_fetchone("SELECT 1 AS exists_flag FROM students LIMIT 1")
    if row:
        return
    payload = []
    for idx, name in enumerate(DEFAULT_STUDENTS, start=1):
        student_id = f"S{idx:03d}"
        payload.append((student_id, name))
    db_executemany("INSERT INTO students (student_id, name) VALUES (?, ?)", payload)


def telegram_enabled() -> bool:
    return bool(
        app.config.get("TELEGRAM_BOT_TOKEN")
        and app.config.get("TELEGRAM_BOT_USERNAME")
        and app.config.get("TELEGRAM_WEBHOOK_SECRET")
    )


def telegram_login_enabled() -> bool:
    return bool(
        app.config.get("TELEGRAM_BOT_TOKEN")
        and app.config.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    )


def telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{app.config['TELEGRAM_BOT_TOKEN']}/{method}"


def send_telegram_message(chat_id: str | int, text: str) -> bool:
    if not app.config.get("TELEGRAM_BOT_TOKEN"):
        return False
    try:
        response = requests.post(
            telegram_api_url("sendMessage"),
            json={"chat_id": chat_id, "text": text},
            timeout=6,
        )
    except requests.RequestException:
        return False
    return response.ok


def verify_telegram_login_payload(user: Dict[str, Any]) -> bool:
    token = app.config.get("TELEGRAM_BOT_TOKEN")
    if not token or not user:
        return False
    try:
        auth_date = int(user.get("auth_date") or 0)
    except (TypeError, ValueError):
        return False
    now_ts = int(time.time())
    ttl = int(app.config.get("TELEGRAM_LOGIN_TTL_SECONDS", 600))
    if auth_date <= 0 or auth_date > now_ts + 60:
        return False
    if now_ts - auth_date > ttl:
        return False

    data: Dict[str, Any] = {}
    for key, value in user.items():
        if key == "hash" or value is None:
            continue
        data[key] = value

    data_check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data.keys()))
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    expected = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    provided = str(user.get("hash") or "")
    return hmac.compare_digest(expected, provided)


def get_active_telegram_token(user_id: str) -> str | None:
    row = db_fetchone(
        """
        SELECT token, expires_at
        FROM telegram_links
        WHERE user_id = ? AND used_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id,),
    )
    if not row:
        return None
    expires_at = row.get("expires_at")
    if expires_at and expires_at < now_iso():
        return None
    return row.get("token")


def create_telegram_token(user_id: str) -> str:
    token = secrets.token_urlsafe(16)
    now = now_iso()
    ttl_minutes = app.config.get("TELEGRAM_TOKEN_TTL_MINUTES", 15)
    expires_at = (datetime.utcnow() + timedelta(minutes=ttl_minutes)).replace(microsecond=0).isoformat() + "Z"
    db_execute(
        "INSERT INTO telegram_links (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now, expires_at),
    )
    return token


def verify_telegram_token(
    token: str | None,
    chat_id: str | int | None,
    username: str | None,
) -> str:
    if not token:
        return "missing"
    row = db_fetchone(
        "SELECT token, user_id, expires_at, used_at FROM telegram_links WHERE token = ?",
        (token,),
    )
    if not row:
        return "invalid"
    if row.get("used_at"):
        return "used"
    expires_at = row.get("expires_at")
    if expires_at and expires_at < now_iso():
        return "expired"
    now = now_iso()
    telegram_id = str(chat_id) if chat_id is not None else None
    telegram_username = (username or "").strip() or None
    db_execute(
        "UPDATE telegram_links SET used_at = ?, telegram_id = ?, telegram_username = ? WHERE token = ?",
        (now, telegram_id, telegram_username, token),
    )
    db_execute(
        "UPDATE users SET telegram_id = ?, telegram_username = ?, telegram_verified_at = ? WHERE id = ?",
        (telegram_id, telegram_username, now, row["user_id"]),
    )
    return "ok"


def hydrate_session_user() -> None:
    user_id = session.get("user_id")
    if not user_id:
        return
    if "role" in session and "telegram_verified" in session and session.get("role") == "admin":
        return
    row = db_fetchone(
        "SELECT role, telegram_verified_at, email FROM users WHERE id = ?",
        (user_id,),
    )
    if not row:
        return
    role = row.get("role")
    email = (row.get("email") or "").lower()
    if email in ADMIN_EMAILS and role != "admin":
        role = "admin"
        db_execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    session["role"] = role
    session["telegram_verified"] = bool(row.get("telegram_verified_at"))


def fetch_summary() -> List[Dict[str, Any]]:
    rows = db_fetchall(
        """
        SELECT s.student_id,
               s.name,
               g.avg_grade,
               g.grades_count,
               a.attendance_rate,
               a.attendance_count
        FROM students s
        LEFT JOIN (
            SELECT student_id,
                   AVG(grade) AS avg_grade,
                   COUNT(*) AS grades_count
            FROM grades
            GROUP BY student_id
        ) g ON g.student_id = s.student_id
        LEFT JOIN (
            SELECT student_id,
                   AVG(CASE WHEN present = 1 THEN 1.0 ELSE 0.0 END) AS attendance_rate,
                   COUNT(*) AS attendance_count
            FROM attendance
            GROUP BY student_id
        ) a ON a.student_id = s.student_id
        ORDER BY s.student_id;
        """
    )

    summary: List[Dict[str, Any]] = []
    for row in rows:
        summary.append(
            {
                "student_id": row["student_id"],
                "name": row["name"],
                "average_grade": round(float(row["avg_grade"] or 0.0), 2),
                "grades_count": int(row["grades_count"] or 0),
                "attendance_rate": round(float(row["attendance_rate"] or 0.0) * 100, 2),
                "attendance_count": int(row["attendance_count"] or 0),
            }
        )
    return summary


def fetch_class_stats() -> Dict[str, Any]:
    row = db_fetchone("SELECT COUNT(*) AS count FROM students")
    students_count = int(row["count"] if row else 0)
    grade_row = db_fetchone(
        "SELECT AVG(grade) AS avg_grade, COUNT(*) AS grades_count FROM grades"
    )
    attendance_row = db_fetchone(
        """
        SELECT AVG(CASE WHEN present = 1 THEN 1.0 ELSE 0.0 END) AS attendance_rate,
               COUNT(*) AS attendance_count
        FROM attendance
        """
    )

    return {
        "students_count": students_count,
        "average_grade": round(float((grade_row or {}).get("avg_grade") or 0.0), 2),
        "grades_count": int((grade_row or {}).get("grades_count") or 0),
        "attendance_rate": round(float((attendance_row or {}).get("attendance_rate") or 0.0) * 100, 2),
        "attendance_count": int((attendance_row or {}).get("attendance_count") or 0),
    }


def get_student(student_id: str) -> Dict[str, Any] | None:
    return db_fetchone(
        "SELECT student_id, name FROM students WHERE student_id = ?",
        (student_id,),
    )


def get_student_stats(student_id: str) -> Dict[str, Any]:
    grade_row = db_fetchone(
        "SELECT AVG(grade) AS avg_grade, COUNT(*) AS grades_count FROM grades WHERE student_id = ?",
        (student_id,),
    )
    attendance_row = db_fetchone(
        """
        SELECT AVG(CASE WHEN present = 1 THEN 1.0 ELSE 0.0 END) AS attendance_rate,
               COUNT(*) AS attendance_count
        FROM attendance
        WHERE student_id = ?
        """,
        (student_id,),
    )
    return {
        "average_grade": round(float((grade_row or {}).get("avg_grade") or 0.0), 2),
        "grades_count": int((grade_row or {}).get("grades_count") or 0),
        "attendance_rate": round(float((attendance_row or {}).get("attendance_rate") or 0.0) * 100, 2),
        "attendance_count": int((attendance_row or {}).get("attendance_count") or 0),
    }


@app.get("/login")
def login() -> str:
    return render_template("login.html", today=date.today().isoformat())


@app.post("/auth/session")
def auth_session() -> tuple[str, int] | tuple[Dict[str, Any], int]:
    payload = request.get_json(silent=True) or {}
    access_token = (payload.get("access_token") or "").strip()
    requested_role = (payload.get("requested_role") or "").strip()
    requested_student_id = (payload.get("student_id") or "").strip()
    if not access_token:
        return jsonify({"error": "missing_token"}), 400

    user = fetch_supabase_user(access_token)
    if not user or not user.get("id"):
        return jsonify({"error": "invalid_token"}), 401

    email = user.get("email") or ""
    state = upsert_user(user["id"], email, requested_role, requested_student_id)
    role = state["role"]
    telegram_verified = state["telegram_verified"]
    session["user_id"] = user["id"]
    session["email"] = email
    session["role"] = role
    session["telegram_verified"] = telegram_verified
    session.permanent = True
    if not telegram_verified:
        redirect_url = url_for("telegram_link")
    else:
        if role == "admin":
            redirect_url = url_for("index")
        elif role == "student":
            redirect_url = url_for("student_portal")
        else:
            redirect_url = url_for("pending")
    return jsonify({"ok": True, "role": role, "redirect": redirect_url}), 200


@app.post("/auth/signup")
def auth_signup() -> tuple[Dict[str, Any], int]:
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    password = (payload.get("password") or "").strip()
    if not email or not password:
        return jsonify({"error": "missing_fields"}), 400

    ok, code = create_supabase_user(email, password)
    if ok:
        return jsonify({"ok": True}), 200
    if code == "admin_signup_disabled":
        return jsonify({"error": "admin_signup_disabled"}), 400
    if code == "user_exists":
        return jsonify({"error": "user_exists"}), 409
    if code == "network":
        return jsonify({"error": "network"}), 502
    return jsonify({"error": "failed"}), 400


@app.post("/auth/telegram")
def auth_telegram() -> tuple[Dict[str, Any], int]:
    if not telegram_login_enabled():
        return jsonify({"error": "telegram_disabled"}), 400
    payload = request.get_json(silent=True) or {}
    user = payload.get("user") or {}
    if not verify_telegram_login_payload(user):
        return jsonify({"error": "invalid_signature"}), 401

    telegram_id = str(user.get("id") or "").strip()
    if not telegram_id:
        return jsonify({"error": "invalid_user"}), 400

    username = (user.get("username") or "").strip()
    first_name = (user.get("first_name") or "").strip()
    last_name = (user.get("last_name") or "").strip()
    display_name = f"{first_name} {last_name}".strip()
    if not display_name:
        display_name = f"@{username}" if username else f"Telegram {telegram_id}"

    requested_role = (payload.get("requested_role") or "").strip()
    student_id = (payload.get("student_id") or "").strip()
    email_label = f"@{username}" if username else f"telegram:{telegram_id}"
    user_key = f"tg:{telegram_id}"

    state = upsert_user(user_key, email_label, requested_role, student_id)
    role = state["role"]
    if telegram_id in ADMIN_TELEGRAM_IDS:
        role = "admin"
        db_execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_key,))

    now = now_iso()
    db_execute(
        "UPDATE users SET telegram_id = ?, telegram_username = ?, telegram_verified_at = ? WHERE id = ?",
        (telegram_id, username or None, now, user_key),
    )

    session["user_id"] = user_key
    session["email"] = display_name
    session["role"] = role
    session["telegram_verified"] = True
    session.permanent = True

    if role == "admin":
        redirect_url = url_for("index")
    elif role == "student":
        redirect_url = url_for("student_portal")
    else:
        redirect_url = url_for("pending")
    return jsonify({"ok": True, "redirect": redirect_url}), 200


@app.get("/logout")
def logout() -> str:
    session.clear()
    return redirect(url_for("login"))


@app.get("/pending")
@login_required
@telegram_required
def pending() -> str:
    if session.get("role") == "student":
        return redirect(url_for("student_portal"))
    return render_template("pending.html", today=date.today().isoformat())


@app.get("/telegram-link")
@login_required
def telegram_link() -> str:
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    row = db_fetchone(
        "SELECT role, telegram_verified_at FROM users WHERE id = ?",
        (user_id,),
    )
    if row and row.get("telegram_verified_at"):
        session["telegram_verified"] = True
        if session.get("role") == "admin":
            redirect_url = url_for("index")
        elif session.get("role") == "student":
            redirect_url = url_for("student_portal")
        else:
            redirect_url = url_for("pending")
        return redirect(redirect_url)

    bot_username = app.config.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    deep_link = None
    if telegram_enabled() and bot_username:
        token = get_active_telegram_token(user_id) or create_telegram_token(user_id)
        deep_link = f"https://t.me/{bot_username}?start={token}"
    return render_template(
        "telegram_link.html",
        today=date.today().isoformat(),
        bot_username=bot_username,
        deep_link=deep_link,
        token_ttl=app.config.get("TELEGRAM_TOKEN_TTL_MINUTES", 15),
    )


@app.get("/student")
@login_required
@telegram_required
def student_portal() -> str:
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    row = db_fetchone("SELECT role, student_id FROM users WHERE id = ?", (user_id,))
    if not row:
        return redirect(url_for("login"))
    if row.get("role") != "student":
        if row.get("role") == "admin":
            return redirect(url_for("index"))
        return redirect(url_for("pending"))

    student_id = row.get("student_id")
    if not student_id:
        return render_template(
            "student_portal.html",
            today=date.today().isoformat(),
            student=None,
            student_id=None,
        )

    student = get_student(student_id)
    if not student:
        return render_template(
            "student_portal.html",
            today=date.today().isoformat(),
            student=None,
            student_id=student_id,
        )

    grades = db_fetchall(
        """
        SELECT id, subject, grade, date, note
        FROM grades
        WHERE student_id = ?
        ORDER BY date DESC, id DESC
        """,
        (student_id,),
    )
    attendance = db_fetchall(
        """
        SELECT id, date, present, note
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC, id DESC
        """,
        (student_id,),
    )
    subjects = db_fetchall(
        """
        SELECT subject, ROUND(AVG(grade), 2) AS average, COUNT(*) AS count
        FROM grades
        WHERE student_id = ?
        GROUP BY subject
        ORDER BY subject
        """,
        (student_id,),
    )
    stats = get_student_stats(student_id)

    return render_template(
        "student.html",
        student=student,
        grades=grades,
        attendance=attendance,
        subjects=subjects,
        stats=stats,
        today=date.today().isoformat(),
    )


@app.get("/telegram/status")
@login_required
def telegram_status() -> tuple[Dict[str, Any], int]:
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"verified": False}), 200
    row = db_fetchone(
        "SELECT role, telegram_verified_at FROM users WHERE id = ?",
        (user_id,),
    )
    verified = bool(row and row.get("telegram_verified_at"))
    if verified:
        session["telegram_verified"] = True
        if row.get("role"):
            session["role"] = row["role"]
        if session.get("role") == "admin":
            redirect_url = url_for("index")
        elif session.get("role") == "student":
            redirect_url = url_for("student_portal")
        else:
            redirect_url = url_for("pending")
        return jsonify({"verified": True, "redirect": redirect_url}), 200
    return jsonify({"verified": False}), 200


@app.post("/telegram/webhook/<secret>")
def telegram_webhook(secret: str) -> tuple[Dict[str, Any], int]:
    if not telegram_enabled() or secret != app.config.get("TELEGRAM_WEBHOOK_SECRET"):
        abort(404)
    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or payload.get("edited_message") or {}
    if not message:
        return jsonify({"ok": True}), 200
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    username = chat.get("username")
    text = (message.get("text") or "").strip()
    if not chat_id:
        return jsonify({"ok": True}), 200

    if text.startswith("/start"):
        token = None
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            token = parts[1].strip()
        result = verify_telegram_token(token, chat_id, username)
        if result == "ok":
            send_telegram_message(chat_id, "Готово! Аккаунт подтверждён. Можно вернуться на сайт.")
        elif result == "expired":
            send_telegram_message(chat_id, "Ссылка устарела. Вернитесь на сайт и получите новую.")
        elif result == "used":
            send_telegram_message(chat_id, "Эта ссылка уже использована. Проверьте статус на сайте.")
        elif result == "invalid":
            send_telegram_message(chat_id, "Не смог найти ссылку. Откройте ссылку с сайта заново.")
        else:
            send_telegram_message(chat_id, "Нужна ссылка с сайта. Откройте её и нажмите Start.")
    else:
        send_telegram_message(chat_id, "Чтобы подтвердить аккаунт, откройте ссылку с сайта и нажмите Start.")

    return jsonify({"ok": True}), 200


@app.get("/invite/<token>")
@login_required
@telegram_required
def accept_invite(token: str) -> str:
    if session.get("role") == "student":
        flash("Инвайты доступны только для учителей.", "error")
        return redirect(url_for("student_portal"))
    row = db_fetchone(
        "SELECT token, expires_at, used_at FROM admin_invites WHERE token = ?",
        (token,),
    )
    if not row:
        flash("Инвайт не найден.", "error")
        return redirect(url_for("pending"))
    if row["used_at"]:
        flash("Инвайт уже использован.", "error")
        return redirect(url_for("pending"))
    expires_at = row["expires_at"]
    if expires_at and expires_at < now_iso():
        flash("Инвайт истёк.", "error")
        return redirect(url_for("pending"))

    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    db_execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    db_execute(
        "UPDATE admin_invites SET used_by = ?, used_at = ? WHERE token = ?",
        (user_id, now_iso(), token),
    )
    session["role"] = "admin"
    flash("Доступ учителя активирован.", "success")
    return redirect(url_for("index"))


@app.get("/admin")
@admin_required
def admin_panel() -> str:
    users = list_users()
    invites = list_invites()
    return render_template(
        "admin.html",
        users=users,
        invites=invites,
        today=date.today().isoformat(),
    )


@app.post("/admin/invites")
@admin_required
def create_invite_route() -> str:
    token = create_invite()
    flash(f"Инвайт создан: {request.url_root}invite/{token}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/")
@admin_required
def index() -> str:
    students = fetch_summary()
    class_stats = fetch_class_stats()
    return render_template(
        "index.html",
        students=students,
        class_stats=class_stats,
        today=date.today().isoformat(),
    )


@app.post("/students")
@admin_required
def add_student() -> str:
    student_id = (request.form.get("student_id") or "").strip()
    name = (request.form.get("name") or "").strip()

    if not student_id or not name:
        flash("Укажите ID и имя ученика.", "error")
        return redirect(url_for("index"))

    try:
        db_execute(
            "INSERT INTO students (student_id, name) VALUES (?, ?)",
            (student_id, name),
        )
        flash("Ученик добавлен.", "success")
    except Exception:
        flash("Ученик с таким ID уже существует.", "error")

    return redirect(url_for("index"))


@app.route("/students/<student_id>")
@admin_required
def student_detail(student_id: str) -> str:
    student = get_student(student_id)
    if not student:
        flash("Ученик не найден.", "error")
        return redirect(url_for("index"))

    grades = db_fetchall(
        """
        SELECT id, subject, grade, date, note
        FROM grades
        WHERE student_id = ?
        ORDER BY date DESC, id DESC
        """,
        (student_id,),
    )
    attendance = db_fetchall(
        """
        SELECT id, date, present, note
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC, id DESC
        """,
        (student_id,),
    )
    subjects = db_fetchall(
        """
        SELECT subject, ROUND(AVG(grade), 2) AS average, COUNT(*) AS count
        FROM grades
        WHERE student_id = ?
        GROUP BY subject
        ORDER BY subject
        """,
        (student_id,),
    )

    stats = get_student_stats(student_id)

    return render_template(
        "student.html",
        student=student,
        grades=grades,
        attendance=attendance,
        subjects=subjects,
        stats=stats,
        today=date.today().isoformat(),
    )


@app.post("/students/<student_id>/grades")
@admin_required
def add_grade(student_id: str) -> str:
    student = get_student(student_id)
    if not student:
        flash("Ученик не найден.", "error")
        return redirect(url_for("index"))

    subject = (request.form.get("subject") or "").strip()
    grade_raw = (request.form.get("grade") or "").strip()
    entry_date = (request.form.get("date") or date.today().isoformat()).strip()
    note = (request.form.get("note") or "").strip() or None

    if not subject or not grade_raw:
        flash("Укажите предмет и оценку.", "error")
        return redirect(url_for("student_detail", student_id=student_id))

    try:
        grade_value = float(grade_raw.replace(",", "."))
    except ValueError:
        flash("Оценка должна быть числом.", "error")
        return redirect(url_for("student_detail", student_id=student_id))

    if not math.isfinite(grade_value):
        flash("Оценка должна быть конечным числом.", "error")
        return redirect(url_for("student_detail", student_id=student_id))

    db_execute(
        "INSERT INTO grades (student_id, subject, grade, date, note) VALUES (?, ?, ?, ?, ?)",
        (student_id, subject, grade_value, entry_date, note),
    )
    flash("Оценка добавлена.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


@app.post("/students/<student_id>/attendance")
@admin_required
def add_attendance(student_id: str) -> str:
    student = get_student(student_id)
    if not student:
        flash("Ученик не найден.", "error")
        return redirect(url_for("index"))

    entry_date = (request.form.get("date") or date.today().isoformat()).strip()
    present_raw = request.form.get("present")
    note = (request.form.get("note") or "").strip() or None

    if present_raw not in {"1", "0"}:
        flash("Выберите статус посещаемости.", "error")
        return redirect(url_for("student_detail", student_id=student_id))

    db_execute(
        "INSERT INTO attendance (student_id, date, present, note) VALUES (?, ?, ?, ?)",
        (student_id, entry_date, int(present_raw), note),
    )
    flash("Посещаемость отмечена.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


if __name__ == "__main__":
    app.run(debug=True)
