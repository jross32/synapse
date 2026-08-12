from scaffold_partials import (auth_fetch_helper, button, card, empty_state, field,
                               message_slot, page)

def landing_page() -> str:
    body = (
        "<h1>Welcome to Our Service</h1>"
        '<p class="lede">Sign up or log in to get started.</p>'
        + card(
            '<form id="landing-form" novalidate>'
            + field("username", "Username", autocomplete="username")
            + field("password", "Password", kind="password", autocomplete="current-password")
            + button("Log In / Sign Up")
            + message_slot("msg")
            + "</form>"
        )
    )

    script = auth_fetch_helper("app_token") + """
if (getToken()) location.href = '/dashboard';

document.getElementById('landing-form').addEventListener('submit', async function (e) {
  e.preventDefault();
  clearMessage('msg');
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();
  if (!username || !password) { showMessage('msg', 'Username and password are required.', 'err'); return; }
  try {
    const response = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username: username, password: password })
    });
    const data = await response.json();
    setToken(data.token);
    location.href = '/dashboard';
  } catch (err) { showMessage('msg', err.message, 'err'); }
});
"""
    return page("Landing Page", body, script=script, brand="Service")

def signup_page() -> str:
    body = (
        "<h1>Sign Up</h1>"
        '<p class="lede">Create an account to get started.</p>'
        + card(
            '<form id="signup-form" novalidate>'
            + field("username", "Username", autocomplete="username")
            + field("email", "Email", kind="email", autocomplete="email")
            + field("password", "Password", kind="password", autocomplete="new-password")
            + button("Sign Up")
            + message_slot("msg")
            + "</form>"
        )
    )

    script = auth_fetch_helper("app_token") + """
document.getElementById('signup-form').addEventListener('submit', async function (e) {
  e.preventDefault();
  clearMessage('msg');
  const username = document.getElementById('username').value.trim();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value.trim();
  if (!username || !email || !password) { showMessage('msg', 'All fields are required.', 'err'); return; }
  try {
    await api('/api/signup', {
      method: 'POST',
      body: JSON.stringify({ username: username, email: email, password: password })
    });
    location.href = '/dashboard';
  } catch (err) { showMessage('msg', err.message, 'err'); }
});
"""
    return page("Sign Up", body, script=script, brand="Service")

def login_page() -> str:
    body = (
        "<h1>Log In</h1>"
        '<p class="lede">Enter your credentials to log in.</p>'
        + card(
            '<form id="login-form" novalidate>'
            + field("username", "Username", autocomplete="username")
            + field("password", "Password", kind="password", autocomplete="current-password")
            + button("Log In")
            + message_slot("msg")
            + "</form>"
        )
    )

    script = auth_fetch_helper("app_token") + """
document.getElementById('login-form').addEventListener('submit', async function (e) {
  e.preventDefault();
  clearMessage('msg');
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();
  if (!username || !password) { showMessage('msg', 'Username and password are required.', 'err'); return; }
  try {
    const response = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username: username, password: password })
    });
    const data = await response.json();
    setToken(data.token);
    location.href = '/dashboard';
  } catch (err) { showMessage('msg', err.message, 'err'); }
});
"""
    return page("Log In", body, script=script, brand="Service")

def dashboard_page() -> str:
    body = (
        "<h1>Dashboard</h1>"
        '<p class="lede">Manage your trails here.</p>'
        + card(
            '<form id="new-trail-form" novalidate>'
            + field("text", "Trail Text", kind="textarea")
            + button("Add Trail")
            + message_slot("msg")
            + "</form>"
        )
        + card('<div id="list">' + empty_state("Loading...") + "</div>")
    )

    script = auth_fetch_helper("app_token") + """
const list = document.getElementById('list');

function render(rows) {
  if (!rows.length) {
    list.innerHTML = '<div class="empty">No trails yet. Add one above.</div>';
    return;
  }
  list.innerHTML = rows.map(function (r) {
    return '<div class="list-row">'
         +   '<div>' + escapeHtml(r.text) + '</div>'
         +   '<button class="btn btn-danger" data-id="' + r.id + '"'
         +   ' aria-label="Delete Trail">Delete</button>'
         + '</div>';
  }).join('');

  list.querySelectorAll('button[data-id]').forEach(function (btn) {
    btn.onclick = async function () {
      try {
        await api('/api/trails/' + btn.dataset.id, { method: 'DELETE' });
        load();
      } catch (err) { showMessage('msg', err.message, 'err'); }
    };
  });
}

async function load() {
  try {
    render(await api('/api/trails'));
  } catch (err) {
    if (/sign in|no longer valid/i.test(err.message)) { clearToken(); location.href = '/login'; }
    else list.innerHTML = '<div class="empty">' + escapeHtml(err.message) + '</div>';
  }
}

document.getElementById('new-trail-form').addEventListener('submit', async function (e) {
  e.preventDefault();
  clearMessage('msg');
  const text = document.getElementById('text').value.trim();
  if (!text) { showMessage('msg', 'Trail text is required.', 'err'); return; }
  try {
    await api('/api/trails', {
      method: 'POST',
      body: JSON.stringify({ text: text })
    });
    showMessage('msg', 'Saved.', 'ok');
    e.target.reset();
    load();
  } catch (err) { showMessage('msg', err.message, 'err'); }
});

load();
"""
    return page("Dashboard", body, script=script, brand="Service")