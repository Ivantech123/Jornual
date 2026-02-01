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

(() => {
  const config = window.__supabase;
  if (!config || !window.supabase) return;

  const client = window.supabase.createClient(config.url, config.key);
  const logoutLink = document.querySelector("[data-logout]");
  if (logoutLink) {
    logoutLink.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await client.auth.signOut();
      } catch (error) {
        // ignore
      }
      window.location.href = logoutLink.href;
    });
  }

  const authForm = document.querySelector("[data-auth-form]");
  if (!authForm) return;

  const status = document.querySelector("[data-auth-status]");
  const actionField = authForm.querySelector("[name='action']");
  const actionButtons = authForm.querySelectorAll("[data-action]");
  actionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (actionField) {
        actionField.value = button.dataset.action || "login";
      }
    });
  });
  const setStatus = (message, isError = false) => {
    if (!status) return;
    status.textContent = message;
    status.style.color = isError ? "#8d2a14" : "";
  };

  const syncSession = async (session) => {
    const response = await fetch("/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: session.access_token }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus("Ошибка авторизации на сервере.", true);
      return;
    }
    window.location.href = payload.redirect || "/";
  };

  client.auth.getSession().then(({ data }) => {
    if (data && data.session) {
      syncSession(data.session);
    }
  });

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = authForm.querySelector("[name='email']").value.trim();
    const password = authForm.querySelector("[name='password']").value;
    const action = (actionField && actionField.value) || "login";

    if (!email || !password) {
      setStatus("Введите email и пароль.", true);
      return;
    }

    setStatus("Проверяем данные...");

    try {
      if (action === "signup") {
        const { data, error } = await client.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/login`,
          },
        });
        if (error) {
          setStatus(error.message, true);
          return;
        }
        if (!data.session) {
          setStatus("Проверьте почту для подтверждения регистрации.");
          return;
        }
        await syncSession(data.session);
      } else {
        const { data, error } = await client.auth.signInWithPassword({ email, password });
        if (error) {
          setStatus(error.message, true);
          return;
        }
        await syncSession(data.session);
      }
    } catch (error) {
      setStatus("Не удалось связаться с Supabase.", true);
    }
  });
})();
