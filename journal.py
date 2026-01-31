#!/usr/bin/env python3
"""Teacher journal for grades and attendance."""
from __future__ import annotations

import argparse
import http.server
import json
import math
import socketserver
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse


def _today() -> str:
    return date_type.today().isoformat()


@dataclass
class GradeEntry:
    subject: str
    grade: float
    date: str
    note: Optional[str] = None


@dataclass
class AttendanceEntry:
    date: str
    present: bool
    note: Optional[str] = None


@dataclass
class StudentRecord:
    student_id: str
    name: str
    grades: List[GradeEntry] = field(default_factory=list)
    attendance: List[AttendanceEntry] = field(default_factory=list)

    def add_grade(self, subject: str, grade: float, entry_date: str, note: Optional[str] = None) -> None:
        self.grades.append(GradeEntry(subject=subject, grade=grade, date=entry_date, note=note))

    def mark_attendance(self, entry_date: str, present: bool, note: Optional[str] = None) -> None:
        self.attendance.append(AttendanceEntry(date=entry_date, present=present, note=note))


class Journal:
    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path
        self.students: Dict[str, StudentRecord] = {}
        if storage_path and storage_path.exists():
            self.load()

    def add_student(self, student_id: str, name: str) -> None:
        if student_id in self.students:
            raise ValueError(f"Student with ID '{student_id}' already exists.")
        self.students[student_id] = StudentRecord(student_id=student_id, name=name)

    def get_student(self, student_id: str) -> StudentRecord:
        try:
            return self.students[student_id]
        except KeyError as exc:
            raise ValueError(f"Student with ID '{student_id}' was not found.") from exc

    def add_grade(
        self,
        student_id: str,
        subject: str,
        grade: float,
        entry_date: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        if not math.isfinite(grade):
            raise ValueError("Grade must be a finite number.")
        student = self.get_student(student_id)
        student.add_grade(subject=subject, grade=grade, entry_date=entry_date or _today(), note=note)

    def mark_attendance(
        self,
        student_id: str,
        present: bool,
        entry_date: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        student = self.get_student(student_id)
        student.mark_attendance(entry_date=entry_date or _today(), present=present, note=note)

    def summary(self) -> Dict[str, Dict[str, float]]:
        report: Dict[str, Dict[str, float]] = {}
        for student_id, student in self.students.items():
            grades = student.grades
            if grades:
                avg_grade = sum(entry.grade for entry in grades) / len(grades)
            else:
                avg_grade = 0.0
            attendance_records = student.attendance
            if attendance_records:
                attendance_rate = sum(1 for entry in attendance_records if entry.present) / len(attendance_records)
            else:
                attendance_rate = 0.0
            report[student_id] = {
                "average_grade": round(avg_grade, 2),
                "attendance_rate": round(attendance_rate * 100, 2),
                "grades_count": len(grades),
                "attendance_count": len(attendance_records),
                "name": student.name,
            }
        return report

    def student_report(self, student_id: str) -> Dict[str, object]:
        student = self.get_student(student_id)
        subject_totals: Dict[str, List[float]] = {}
        for entry in student.grades:
            subject_totals.setdefault(entry.subject, []).append(entry.grade)

        subject_averages = {
            subject: round(sum(values) / len(values), 2) for subject, values in subject_totals.items()
        }
        grades_sorted = sorted(student.grades, key=lambda entry: entry.date)
        attendance_sorted = sorted(student.attendance, key=lambda entry: entry.date)
        return {
            "student_id": student.student_id,
            "name": student.name,
            "grades": grades_sorted,
            "attendance": attendance_sorted,
            "subject_averages": subject_averages,
        }

    def student_report_dict(self, student_id: str) -> Dict[str, object]:
        report = self.student_report(student_id)
        return {
            "student_id": report["student_id"],
            "name": report["name"],
            "grades": [entry.__dict__ for entry in report["grades"]],
            "attendance": [entry.__dict__ for entry in report["attendance"]],
            "subject_averages": report["subject_averages"],
        }

    def to_dict(self) -> Dict[str, dict]:
        return {
            student_id: {
                "student_id": student.student_id,
                "name": student.name,
                "grades": [entry.__dict__ for entry in student.grades],
                "attendance": [entry.__dict__ for entry in student.attendance],
            }
            for student_id, student in self.students.items()
        }

    def save(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        self.storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self.storage_path:
            return
        data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self.students = {}
        for student_id, payload in data.items():
            record = StudentRecord(student_id=student_id, name=payload["name"])
            for grade in payload.get("grades", []):
                record.add_grade(
                    subject=grade["subject"],
                    grade=grade["grade"],
                    entry_date=grade["date"],
                    note=grade.get("note"),
                )
            for attendance in payload.get("attendance", []):
                record.mark_attendance(
                    entry_date=attendance["date"],
                    present=attendance["present"],
                    note=attendance.get("note"),
                )
            self.students[student_id] = record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Teacher journal for grades and attendance.")
    parser.add_argument("--storage", default="journal.json", help="Path to JSON storage file.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_student_parser = subparsers.add_parser("add-student", help="Add a new student.")
    add_student_parser.add_argument("student_id")
    add_student_parser.add_argument("name")

    add_grade_parser = subparsers.add_parser("add-grade", help="Add a grade for a student.")
    add_grade_parser.add_argument("student_id")
    add_grade_parser.add_argument("subject")
    add_grade_parser.add_argument("grade", type=float)
    add_grade_parser.add_argument("--date", default=_today())
    add_grade_parser.add_argument("--note")

    attendance_parser = subparsers.add_parser("mark-attendance", help="Mark attendance for a student.")
    attendance_parser.add_argument("student_id")
    attendance_parser.add_argument("--present", action="store_true")
    attendance_parser.add_argument("--absent", action="store_true")
    attendance_parser.add_argument("--date", default=_today())
    attendance_parser.add_argument("--note")

    subparsers.add_parser("summary", help="Show summary for all students.")
    subparsers.add_parser("list", help="List all students.")
    show_student_parser = subparsers.add_parser("show-student", help="Show a student report.")
    show_student_parser.add_argument("student_id")
    show_student_parser.add_argument("--with-notes", action="store_true")

    serve_parser = subparsers.add_parser("serve", help="Run the web interface.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    return parser


def run_server(journal: Journal, host: str, port: int) -> None:
    web_root = Path(__file__).parent / "web"

    class JournalRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(web_root), **kwargs)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if not length:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)

        def _send_error(self, message: str, status: int = 400) -> None:
            self._send_json({"error": message}, status=status)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/summary":
                self._send_json(journal.summary())
                return
            if parsed.path == "/api/students":
                students = [
                    {"student_id": student.student_id, "name": student.name}
                    for student in sorted(journal.students.values(), key=lambda item: item.student_id)
                ]
                self._send_json({"students": students})
                return
            if parsed.path.startswith("/api/students/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 3:
                    student_id = parts[2]
                    try:
                        self._send_json(journal.student_report_dict(student_id))
                    except ValueError as exc:
                        self._send_error(str(exc), status=404)
                    return
            super().do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_error("Invalid JSON payload.")
                return

            if parsed.path == "/api/students":
                try:
                    journal.add_student(payload["student_id"], payload["name"])
                    journal.save()
                    self._send_json({"status": "ok"}, status=201)
                except (KeyError, ValueError) as exc:
                    self._send_error(str(exc))
                return

            if parsed.path.startswith("/api/students/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 4 and parts[2] and parts[3] in {"grades", "attendance"}:
                    student_id = parts[2]
                    if parts[3] == "grades":
                        try:
                            journal.add_grade(
                                student_id=student_id,
                                subject=payload["subject"],
                                grade=float(payload["grade"]),
                                entry_date=payload.get("date"),
                                note=payload.get("note"),
                            )
                            journal.save()
                            self._send_json({"status": "ok"}, status=201)
                        except (KeyError, ValueError) as exc:
                            self._send_error(str(exc))
                        return
                    if parts[3] == "attendance":
                        try:
                            journal.mark_attendance(
                                student_id=student_id,
                                present=bool(payload["present"]),
                                entry_date=payload.get("date"),
                                note=payload.get("note"),
                            )
                            journal.save()
                            self._send_json({"status": "ok"}, status=201)
                        except (KeyError, ValueError) as exc:
                            self._send_error(str(exc))
                        return

            self._send_error("Not found.", status=404)

    with socketserver.ThreadingTCPServer((host, port), JournalRequestHandler) as httpd:
        print(f"Serving journal on http://{host}:{port}")
        httpd.serve_forever()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    storage = Path(args.storage)
    journal = Journal(storage)

    if args.command == "add-student":
        journal.add_student(args.student_id, args.name)
        journal.save()
        print(f"Added student {args.name} ({args.student_id}).")
        return

    if args.command == "add-grade":
        journal.add_grade(args.student_id, args.subject, args.grade, args.date, args.note)
        journal.save()
        print(f"Added grade {args.grade} for {args.student_id} in {args.subject}.")
        return

    if args.command == "mark-attendance":
        if args.absent and args.present:
            raise SystemExit("Use only one of --present or --absent.")
        if not args.absent and not args.present:
            raise SystemExit("Specify --present or --absent.")
        present = not args.absent
        journal.mark_attendance(args.student_id, present, args.date, args.note)
        journal.save()
        status = "present" if present else "absent"
        print(f"Marked {args.student_id} as {status} on {args.date}.")
        return

    if args.command == "summary":
        summary = journal.summary()
        if not summary:
            print("No students added yet.")
            return
        for student_id, info in summary.items():
            print(
                f"{info['name']} ({student_id}): avg grade {info['average_grade']} "
                f"({info['grades_count']} entries), attendance {info['attendance_rate']}% "
                f"({info['attendance_count']} entries)"
            )
        return

    if args.command == "list":
        if not journal.students:
            print("No students added yet.")
            return
        for student in sorted(journal.students.values(), key=lambda item: item.student_id):
            print(f"{student.student_id}: {student.name}")
        return

    if args.command == "show-student":
        report = journal.student_report(args.student_id)
        print(f"{report['name']} ({report['student_id']})")
        subject_averages = report["subject_averages"]
        if subject_averages:
            print("Subject averages:")
            for subject, average in sorted(subject_averages.items()):
                print(f"  {subject}: {average}")
        else:
            print("No grades recorded yet.")

        grades = report["grades"]
        if grades:
            print("Grades:")
            for entry in grades:
                note_suffix = f" ({entry.note})" if entry.note and args.with_notes else ""
                print(f"  {entry.date} - {entry.subject}: {entry.grade}{note_suffix}")
        attendance = report["attendance"]
        if attendance:
            print("Attendance:")
            for entry in attendance:
                status = "present" if entry.present else "absent"
                note_suffix = f" ({entry.note})" if entry.note and args.with_notes else ""
                print(f"  {entry.date} - {status}{note_suffix}")
        else:
            print("No attendance records yet.")
        return

    if args.command == "serve":
        run_server(journal, args.host, args.port)
        return


if __name__ == "__main__":
    main()
