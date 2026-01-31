const statusEl = document.getElementById("status");
const studentsList = document.getElementById("students-list");
const summaryBody = document.getElementById("summary-body");
const reportSelect = document.getElementById("report-student");
const reportButton = document.getElementById("refresh-report");
const reportContent = document.getElementById("report-content");

const studentForm = document.getElementById("student-form");
const gradeForm = document.getElementById("grade-form");
const attendanceForm = document.getElementById("attendance-form");

const state = {
  students: [],
};

const showStatus = (message, isError = false) => {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#b91c1c" : "#6b7280";
};

const requestJson = async (url, options = {}) => {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Ошибка запроса.");
  }
  return payload;
};

const loadStudents = async () => {
  const data = await requestJson("/api/students");
  state.students = data.students;
  studentsList.innerHTML = "";
  data.students.forEach((student) => {
    const item = document.createElement("li");
    item.textContent = `${student.name} (${student.student_id})`;
    studentsList.appendChild(item);
  });

  const selects = document.querySelectorAll("select[name='student_id'], #report-student");
  selects.forEach((select) => {
    select.innerHTML = "";
    data.students.forEach((student) => {
      const option = document.createElement("option");
      option.value = student.student_id;
      option.textContent = `${student.name} (${student.student_id})`;
      select.appendChild(option);
    });
  });
};

const loadSummary = async () => {
  const summary = await requestJson("/api/summary");
  summaryBody.innerHTML = "";
  const entries = Object.entries(summary);
  if (!entries.length) {
    summaryBody.innerHTML = "<tr><td colspan='5'>Нет данных.</td></tr>";
    return;
  }
  entries.forEach(([studentId, info]) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${info.name} (${studentId})</td>
      <td>${info.average_grade}</td>
      <td>${info.grades_count}</td>
      <td>${info.attendance_rate}%</td>
      <td>${info.attendance_count}</td>
    `;
    summaryBody.appendChild(row);
  });
};

const renderReport = (report) => {
  reportContent.innerHTML = "";
  if (!report) {
    reportContent.textContent = "Нет данных по ученику.";
    return;
  }

  const averages = Object.entries(report.subject_averages);
  const grades = report.grades || [];
  const attendance = report.attendance || [];

  const averagesSection = document.createElement("div");
  averagesSection.className = "report-section";
  averagesSection.innerHTML = `
    <strong>Средние по предметам</strong>
    <ul>${averages.length ? averages.map(([subject, avg]) => `<li>${subject}: ${avg}</li>`).join("") : "<li>Нет оценок.</li>"}</ul>
  `;

  const gradesSection = document.createElement("div");
  gradesSection.className = "report-section";
  gradesSection.innerHTML = `
    <strong>Оценки</strong>
    <ul>${grades.length ? grades.map((entry) => `<li>${entry.date} — ${entry.subject}: ${entry.grade}${entry.note ? ` (${entry.note})` : ""}</li>`).join("") : "<li>Нет оценок.</li>"}</ul>
  `;

  const attendanceSection = document.createElement("div");
  attendanceSection.className = "report-section";
  attendanceSection.innerHTML = `
    <strong>Посещаемость</strong>
    <ul>${attendance.length ? attendance.map((entry) => `<li>${entry.date} — ${entry.present ? "присутствовал" : "отсутствовал"}${entry.note ? ` (${entry.note})` : ""}</li>`).join("") : "<li>Нет отметок.</li>"}</ul>
  `;

  reportContent.append(averagesSection, gradesSection, attendanceSection);
};

const loadReport = async () => {
  const studentId = reportSelect.value;
  if (!studentId) {
    reportContent.textContent = "Сначала добавьте ученика.";
    return;
  }
  const report = await requestJson(`/api/students/${studentId}`);
  renderReport(report);
};

studentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(studentForm);
  const payload = Object.fromEntries(formData.entries());
  try {
    await requestJson("/api/students", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    studentForm.reset();
    showStatus("Ученик добавлен.");
    await loadStudents();
    await loadSummary();
    await loadReport();
  } catch (error) {
    showStatus(error.message, true);
  }
});

gradeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(gradeForm);
  const payload = Object.fromEntries(formData.entries());
  const studentId = payload.student_id;
  payload.grade = Number(payload.grade);
  if (!payload.date) {
    delete payload.date;
  }
  if (!payload.note) {
    delete payload.note;
  }
  try {
    await requestJson(`/api/students/${studentId}/grades`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    gradeForm.reset();
    showStatus("Оценка добавлена.");
    await loadSummary();
    await loadReport();
  } catch (error) {
    showStatus(error.message, true);
  }
});

attendanceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(attendanceForm);
  const payload = Object.fromEntries(formData.entries());
  const studentId = payload.student_id;
  payload.present = payload.present === "true";
  if (!payload.date) {
    delete payload.date;
  }
  if (!payload.note) {
    delete payload.note;
  }
  try {
    await requestJson(`/api/students/${studentId}/attendance`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    attendanceForm.reset();
    showStatus("Посещаемость сохранена.");
    await loadSummary();
    await loadReport();
  } catch (error) {
    showStatus(error.message, true);
  }
});

reportButton.addEventListener("click", async () => {
  try {
    await loadReport();
  } catch (error) {
    showStatus(error.message, true);
  }
});

const init = async () => {
  try {
    await loadStudents();
    await loadSummary();
    await loadReport();
  } catch (error) {
    showStatus(error.message, true);
  }
};

init();
