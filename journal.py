#!/usr/bin/env python3
"""Teacher journal for grades and attendance."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path
from typing import Dict, List, Optional


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
                "name": student.name,
            }
        return report

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

    return parser


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
        present = True
        if args.absent:
            present = False
        elif args.present:
            present = True
        else:
            raise SystemExit("Specify --present or --absent.")
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
                f"{info['name']} ({student_id}): avg grade {info['average_grade']}, "
                f"attendance {info['attendance_rate']}%"
            )
        return

    if args.command == "list":
        if not journal.students:
            print("No students added yet.")
            return
        for student in journal.students.values():
            print(f"{student.student_id}: {student.name}")
        return


if __name__ == "__main__":
    main()
