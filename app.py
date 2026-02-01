from __future__ import annotations

import math
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, flash, g, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "journal.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("JOURNAL_SECRET", "dev-key-change-me")
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


def configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 3000")


def ensure_schema() -> None:
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
        """
    )
    conn.commit()
    conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
        configure_connection(db)
        g.db = db
    return g.db


@app.teardown_appcontext
def close_db(exception: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def seed_students_if_empty() -> None:
    db_path: Path = app.config["DATABASE"]
    conn = sqlite3.connect(db_path)
    configure_connection(conn)
    exists = conn.execute("SELECT 1 FROM students LIMIT 1").fetchone()
    if exists:
        conn.close()
        return
    payload = []
    for idx, name in enumerate(DEFAULT_STUDENTS, start=1):
        student_id = f"S{idx:03d}"
        payload.append((student_id, name))
    conn.executemany("INSERT INTO students (student_id, name) VALUES (?, ?)", payload)
    conn.commit()
    conn.close()



def fetch_summary() -> List[Dict[str, Any]]:
    db = get_db()
    rows = db.execute(
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
    ).fetchall()

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
    db = get_db()
    students_count = int(db.execute("SELECT COUNT(*) FROM students").fetchone()[0])
    grade_row = db.execute(
        "SELECT AVG(grade) AS avg_grade, COUNT(*) AS grades_count FROM grades"
    ).fetchone()
    attendance_row = db.execute(
        """
        SELECT AVG(CASE WHEN present = 1 THEN 1.0 ELSE 0.0 END) AS attendance_rate,
               COUNT(*) AS attendance_count
        FROM attendance
        """
    ).fetchone()

    return {
        "students_count": students_count,
        "average_grade": round(float(grade_row["avg_grade"] or 0.0), 2),
        "grades_count": int(grade_row["grades_count"] or 0),
        "attendance_rate": round(float(attendance_row["attendance_rate"] or 0.0) * 100, 2),
        "attendance_count": int(attendance_row["attendance_count"] or 0),
    }


def fetch_attendance_trend(limit: int = 7) -> List[Dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT date,
               AVG(CASE WHEN present = 1 THEN 1.0 ELSE 0.0 END) AS attendance_rate,
               COUNT(*) AS attendance_count
        FROM attendance
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    trend = [
        {
            "date": row["date"],
            "rate": round(float(row["attendance_rate"] or 0.0) * 100, 2),
            "count": int(row["attendance_count"] or 0),
        }
        for row in rows
    ]
    return list(reversed(trend))



def get_student(student_id: str) -> sqlite3.Row | None:
    return get_db().execute(
        "SELECT student_id, name FROM students WHERE student_id = ?",
        (student_id,),
    ).fetchone()



def get_student_stats(student_id: str) -> Dict[str, Any]:
    db = get_db()
    grade_row = db.execute(
        "SELECT AVG(grade) AS avg_grade, COUNT(*) AS grades_count FROM grades WHERE student_id = ?",
        (student_id,),
    ).fetchone()
    attendance_row = db.execute(
        """
        SELECT AVG(CASE WHEN present = 1 THEN 1.0 ELSE 0.0 END) AS attendance_rate,
               COUNT(*) AS attendance_count
        FROM attendance
        WHERE student_id = ?
        """,
        (student_id,),
    ).fetchone()
    return {
        "average_grade": round(float(grade_row["avg_grade"] or 0.0), 2),
        "grades_count": int(grade_row["grades_count"] or 0),
        "attendance_rate": round(float(attendance_row["attendance_rate"] or 0.0) * 100, 2),
        "attendance_count": int(attendance_row["attendance_count"] or 0),
    }


@app.route("/")
def index() -> str:
    students = fetch_summary()
    class_stats = fetch_class_stats()
    attendance_trend = fetch_attendance_trend()
    return render_template(
        "index.html",
        students=students,
        class_stats=class_stats,
        attendance_trend=attendance_trend,
        today=date.today().isoformat(),
    )


@app.post("/students")
def add_student() -> str:
    student_id = (request.form.get("student_id") or "").strip()
    name = (request.form.get("name") or "").strip()

    if not student_id or not name:
        flash("Укажите ID и имя ученика.", "error")
        return redirect(url_for("index"))

    try:
        get_db().execute(
            "INSERT INTO students (student_id, name) VALUES (?, ?)",
            (student_id, name),
        )
        get_db().commit()
        flash("Ученик добавлен.", "success")
    except sqlite3.IntegrityError:
        flash("Ученик с таким ID уже существует.", "error")

    return redirect(url_for("index"))


@app.get("/students/open")
def open_student() -> str:
    student_id = (request.args.get("student_id") or "").strip()
    if not student_id:
        flash("Выберите ученика.", "error")
        return redirect(url_for("index"))
    return redirect(url_for("student_detail", student_id=student_id))


@app.route("/students/<student_id>")
def student_detail(student_id: str) -> str:
    student = get_student(student_id)
    if not student:
        flash("Ученик не найден.", "error")
        return redirect(url_for("index"))

    db = get_db()
    grades = db.execute(
        """
        SELECT id, subject, grade, date, note
        FROM grades
        WHERE student_id = ?
        ORDER BY date DESC, id DESC
        """,
        (student_id,),
    ).fetchall()
    attendance = db.execute(
        """
        SELECT id, date, present, note
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC, id DESC
        """,
        (student_id,),
    ).fetchall()
    subjects = db.execute(
        """
        SELECT subject, ROUND(AVG(grade), 2) AS average, COUNT(*) AS count
        FROM grades
        WHERE student_id = ?
        GROUP BY subject
        ORDER BY subject
        """,
        (student_id,),
    ).fetchall()

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

    get_db().execute(
        "INSERT INTO grades (student_id, subject, grade, date, note) VALUES (?, ?, ?, ?, ?)",
        (student_id, subject, grade_value, entry_date, note),
    )
    get_db().commit()
    flash("Оценка добавлена.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


@app.post("/students/<student_id>/attendance")
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

    get_db().execute(
        "INSERT INTO attendance (student_id, date, present, note) VALUES (?, ?, ?, ?)",
        (student_id, entry_date, int(present_raw), note),
    )
    get_db().commit()
    flash("Посещаемость отмечена.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


@app.post("/attendance/quick")
def add_attendance_quick() -> str:
    student_id = (request.form.get("student_id") or "").strip()
    entry_date = (request.form.get("date") or date.today().isoformat()).strip()
    present_raw = request.form.get("present")
    note = (request.form.get("note") or "").strip() or None

    if not student_id:
        flash("Выберите ученика.", "error")
        return redirect(url_for("index"))
    if present_raw not in {"1", "0"}:
        flash("Выберите статус посещаемости.", "error")
        return redirect(url_for("index"))
    if not get_student(student_id):
        flash("Ученик не найден.", "error")
        return redirect(url_for("index"))

    get_db().execute(
        "INSERT INTO attendance (student_id, date, present, note) VALUES (?, ?, ?, ?)",
        (student_id, entry_date, int(present_raw), note),
    )
    get_db().commit()
    flash("Посещаемость отмечена.", "success")
    return redirect(url_for("index"))


ensure_schema()
seed_students_if_empty()


if __name__ == "__main__":
    app.run(debug=True)
