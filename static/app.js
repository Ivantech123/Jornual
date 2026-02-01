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
  const title = document.querySelector("[data-auth-title]");
  const subtitle = document.querySelector("[data-auth-subtitle]");
  const note = document.querySelector("[data-auth-note]");
  const submit = authForm.querySelector("[data-auth-submit]");
  const tabs = document.querySelectorAll("[data-auth-mode]");
  const signupOnly = authForm.querySelectorAll(".only-signup");

  const setMode = (mode) => {
    const isSignup = mode === "signup";
    if (actionField) actionField.value = mode;
    if (submit) submit.textContent = isSignup ? "Создать аккаунт" : "Войти";
    if (title) title.textContent = isSignup ? "Регистрация" : "Вход в журнал";
    if (subtitle) {
      subtitle.textContent = isSignup
        ? "Создайте аккаунт. Доступ к журналу выдаётся по инвайту."
        : "Авторизация для учителей. Доступ к журналу по инвайту.";
    }
    if (note) {
      note.style.display = isSignup ? "block" : "none";
    }
    signupOnly.forEach((field) => {
      field.style.display = isSignup ? "block" : "none";
    });
    tabs.forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.authMode === mode);
    });
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      setMode(tab.dataset.authMode || "login");
    });
  });

  setMode((actionField && actionField.value) || "login");
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
    const confirm = authForm.querySelector("[name='password_confirm']");

    if (!email || !password) {
      setStatus("Введите email и пароль.", true);
      return;
    }

    setStatus("Проверяем данные...");

    try {
      if (action === "signup" && confirm && password !== confirm.value) {
        setStatus("Пароли не совпадают.", true);
        return;
      }
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
