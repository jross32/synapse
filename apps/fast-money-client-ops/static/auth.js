let cachedLocalSession = null;
let localSessionLoaded = false;

async function authJson(path, options) {
  const response = await fetch(path, Object.assign({
    headers: { Accept: "application/json" },
    cache: "no-store",
  }, options || {}));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || "Local session request failed.");
  }
  return payload;
}

async function loadLocalSession(force) {
  if (localSessionLoaded && !force) return cachedLocalSession;
  const payload = await authJson("/api/session");
  cachedLocalSession = payload.session || null;
  localSessionLoaded = true;
  return cachedLocalSession;
}

async function getCsrfToken() {
  const session = await loadLocalSession(false);
  return session && session.csrf_token ? session.csrf_token : null;
}

function setSigninStatus(message, tone) {
  const status = document.getElementById("signin-status");
  if (!status) return;
  status.textContent = message || "";
  status.dataset.tone = tone || "neutral";
}

async function signInAs(role, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Starting session...";
  try {
    const payload = await authJson("/api/session/login", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ role }),
    });
    cachedLocalSession = payload.session || null;
    localSessionLoaded = true;
    const session = cachedLocalSession || {};
    window.location.assign(session.role === "operator" ? "/ops" : "/portal");
  } catch (error) {
    button.disabled = false;
    button.textContent = original;
    setSigninStatus(error.message || "Could not start the local session.", "error");
  }
}

async function signOut(button) {
  if (button) {
    button.disabled = true;
    button.textContent = "Signing out...";
  }
  try {
    const csrfToken = await getCsrfToken();
    if (csrfToken) {
      await authJson("/api/session/logout", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": csrfToken,
        },
      });
    }
  } finally {
    cachedLocalSession = null;
    localSessionLoaded = true;
    window.location.assign("/signin");
  }
}

function bindRoleButtons() {
  document.querySelectorAll("[data-local-role]").forEach((button) => {
    button.addEventListener("click", () => {
      signInAs(button.dataset.localRole || "", button);
    });
  });
}

function bindSignOutButtons() {
  document.querySelectorAll("[data-signout]").forEach((button) => {
    button.addEventListener("click", () => signOut(button));
  });
}

async function bootstrapLocalAuth() {
  bindRoleButtons();
  bindSignOutButtons();

  try {
    const session = await loadLocalSession(true);
    document.querySelectorAll("[data-session-label]").forEach((node) => {
      node.textContent = session
        ? session.display_name + " - " + session.role
        : "No active session";
    });
    if (document.body.dataset.page === "signin" && session) {
      setSigninStatus(
        "A " + session.role + " session is already active. Choose a role below to switch.",
        "success"
      );
    }
  } catch (error) {
    if (document.body.dataset.page === "signin") {
      setSigninStatus("Local session service is unavailable.", "error");
    }
  }
}

window.fastMoneyAuth = {
  getCsrfToken,
  getSession: () => loadLocalSession(false),
};

bootstrapLocalAuth();
