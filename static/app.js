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
  const roleInputs = authForm.querySelectorAll("[name='account_role']");
  const studentIdField = authForm.querySelector("[name='student_id']");
  const card = document.querySelector("[data-auth-card]");

  const updateRoleView = () => {
    const role = authForm.querySelector("[name='account_role']:checked")?.value || "teacher";
    authForm.classList.toggle("is-student", role === "student");
    if (note) {
      note.textContent =
        role === "student"
          ? "После регистрации подтвердите доступ через Telegram. Профиль привяжет учитель."
          : "После регистрации подтвердите доступ через Telegram.";
    }
  };

  const setMode = (mode) => {
    const isSignup = mode === "signup";
    if (actionField) actionField.value = mode;
    authForm.classList.toggle("is-signup", isSignup);
    if (submit) submit.textContent = isSignup ? "Создать аккаунт" : "Войти";
    if (title) title.textContent = isSignup ? "Регистрация" : "Вход в журнал";
    if (subtitle) {
      subtitle.textContent = isSignup
        ? "Создайте аккаунт. Подтверждение доступа проходит через Telegram."
        : "Авторизация для учителей. Доступ по инвайту и подтверждению в Telegram.";
    }
    if (note) {
      note.style.display = isSignup ? "block" : "none";
    }
    signupOnly.forEach((field) => {
      field.style.display = "block";
    });
    tabs.forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.authMode === mode);
    });
    if (card) {
      card.classList.remove("is-switching");
      void card.offsetWidth;
      card.classList.add("is-switching");
    }
    updateRoleView();
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      setMode(tab.dataset.authMode || "login");
    });
  });

  roleInputs.forEach((input) => {
    input.addEventListener("change", updateRoleView);
  });

  setMode((actionField && actionField.value) || "login");
  const setStatus = (message, isError = false) => {
    if (!status) return;
    status.textContent = message;
    status.style.color = isError ? "#8d2a14" : "";
  };

  const syncSession = async (session, extra = {}) => {
    const response = await fetch("/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: session.access_token, ...extra }),
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
      if (submit) {
        submit.classList.add("is-pressed");
        setTimeout(() => submit.classList.remove("is-pressed"), 220);
      }
      if (action === "signup" && confirm && password !== confirm.value) {
        setStatus("Пароли не совпадают.", true);
        return;
      }
      if (action === "signup") {
        setStatus("Создаём аккаунт...");
        let adminSignup = false;
        const selectedRole = authForm.querySelector("[name='account_role']:checked")?.value || "teacher";
        const studentId = (studentIdField && studentIdField.value.trim()) || "";
        try {
          const response = await fetch("/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });
          if (response.ok) {
            adminSignup = true;
          } else {
            const payload = await response.json().catch(() => ({}));
            if (payload.error === "admin_signup_disabled") {
              adminSignup = false;
            } else if (payload.error === "user_exists") {
              adminSignup = true;
            } else if (payload.error === "network") {
              setStatus("Сервер регистрации недоступен. Попробуйте ещё раз.", true);
              return;
            } else {
              setStatus("Не удалось создать аккаунт. Проверьте данные.", true);
              return;
            }
          }
        } catch (error) {
          setStatus("Не удалось создать аккаунт. Попробуйте позже.", true);
          return;
        }

        if (!adminSignup) {
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
            setStatus("Регистрация создана. Подтвердите доступ в Telegram или проверьте настройки подтверждения email.");
            return;
          }
          await syncSession(data.session, {
            requested_role: selectedRole,
            student_id: studentId,
          });
          return;
        }

        const { data, error } = await client.auth.signInWithPassword({ email, password });
        if (error) {
          setStatus(error.message, true);
          return;
        }
        await syncSession(data.session, {
          requested_role: selectedRole,
          student_id: studentId,
        });
      } else {
        const { data, error } = await client.auth.signInWithPassword({ email, password });
        if (error) {
          setStatus(error.message, true);
          return;
        }
        await syncSession(data.session);
      }
    } catch (error) {
      setStatus("Не удалось связаться с сервером авторизации.", true);
    }
  });
})();

(() => {
  const telegramBlock = document.querySelector("[data-telegram-block]");
  if (!telegramBlock) return;
})();

(() => {
  const telegramPage = document.querySelector("[data-telegram-page]");
  if (!telegramPage) return;

  const statusEl = telegramPage.querySelector("[data-telegram-status]");
  const refreshBtn = telegramPage.querySelector("[data-telegram-refresh]");
  const statusUrl = telegramPage.dataset.statusUrl || "/telegram/status";
  let inFlight = false;

  const setStatus = (message) => {
    if (statusEl) statusEl.textContent = message;
  };

  const checkStatus = async (manual = false) => {
    if (inFlight) return;
    inFlight = true;
    try {
      const response = await fetch(statusUrl, { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (data.verified) {
        setStatus("Подтверждение получено. Перенаправляем…");
        window.location.href = data.redirect || "/pending";
        return;
      }
      if (manual) {
        setStatus("Пока не подтверждено. Проверьте Telegram и попробуйте снова.");
      }
    } catch (error) {
      if (manual) {
        setStatus("Не удалось проверить статус. Попробуйте ещё раз.");
      }
    } finally {
      inFlight = false;
    }
  };

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => checkStatus(true));
  }

  checkStatus(false);
  setInterval(() => checkStatus(false), 3000);
})();
