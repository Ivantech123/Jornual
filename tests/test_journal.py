import json
import tempfile
import unittest
from pathlib import Path

from journal import Journal


class JournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "journal.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_student_and_persist(self) -> None:
        journal = Journal(self.storage_path)
        journal.add_student("S001", "Иван Петров")
        journal.save()

        loaded = Journal(self.storage_path)
        self.assertIn("S001", loaded.students)
        self.assertEqual(loaded.get_student("S001").name, "Иван Петров")

    def test_add_grade_and_summary(self) -> None:
        journal = Journal(self.storage_path)
        journal.add_student("S001", "Иван Петров")
        journal.add_grade("S001", "Математика", 4.5, "2024-09-01")
        journal.add_grade("S001", "Математика", 5.0, "2024-09-02")

        summary = journal.summary()
        self.assertEqual(summary["S001"]["average_grade"], 4.75)
        self.assertEqual(summary["S001"]["grades_count"], 2)

    def test_mark_attendance(self) -> None:
        journal = Journal(self.storage_path)
        journal.add_student("S002", "Мария Смирнова")
        journal.mark_attendance("S002", True, "2024-09-01")
        journal.mark_attendance("S002", False, "2024-09-02")

        summary = journal.summary()
        self.assertEqual(summary["S002"]["attendance_rate"], 50.0)
        self.assertEqual(summary["S002"]["attendance_count"], 2)

    def test_student_report_dict(self) -> None:
        journal = Journal(self.storage_path)
        journal.add_student("S003", "Алексей Иванов")
        journal.add_grade("S003", "Физика", 4.0, "2024-09-03", "контрольная")
        journal.mark_attendance("S003", True, "2024-09-03", "вовремя")

        report = journal.student_report_dict("S003")
        self.assertEqual(report["student_id"], "S003")
        self.assertEqual(report["subject_averages"]["Физика"], 4.0)
        self.assertEqual(report["grades"][0]["note"], "контрольная")
        self.assertTrue(report["attendance"][0]["present"])

    def test_save_serialization(self) -> None:
        journal = Journal(self.storage_path)
        journal.add_student("S004", "Ольга Миронова")
        journal.add_grade("S004", "История", 5.0, "2024-09-04")
        journal.save()

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self.assertIn("S004", payload)
        self.assertEqual(payload["S004"]["grades"][0]["subject"], "История")


if __name__ == "__main__":
    unittest.main()
