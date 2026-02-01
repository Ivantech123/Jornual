(() => {
  const filter = document.querySelector("#studentFilter");
  if (!filter) return;

  const rows = Array.from(document.querySelectorAll(".student-row"));
  const normalize = (value) => value.toLowerCase().trim();

  filter.addEventListener("input", () => {
    const query = normalize(filter.value);
    rows.forEach((row) => {
      const name = row.dataset.name || "";
      const id = row.dataset.id || "";
      const visible = !query || name.includes(query) || id.includes(query);
      row.style.display = visible ? "" : "none";
    });
  });
})();
