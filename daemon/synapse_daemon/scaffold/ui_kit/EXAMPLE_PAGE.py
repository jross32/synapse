"""A worked page in the house style, shown to the model as an example.

Instructions underperform examples for small models — and a longer instruction block measurably
made a 1.5B model *worse* (33% to 0%), because prompt text crowds out its context. So the house
style is taught by demonstration: one page that uses every partial correctly, short enough to
sit in a prompt without displacing the actual task.

Everything a generated page needs to get right appears here once: labelled inputs, a message
slot, escaping on render, and the auth helper.
"""

from scaffold_partials import (auth_fetch_helper, button, card, empty_state, field,
                               message_slot, page)


def notes_page() -> str:
    """A list page with a create form — the shape most dashboards take."""
    body = (
        "<h1>Your notes</h1>"
        '<p class="lede">Anything you save here is private to your account.</p>'
        + card(
            '<form id="new-note" novalidate>'
            + field("title", "Title", autocomplete="off")
            + field("body", "Note", kind="text", required=False)
            + button("Save note")
            + message_slot("msg")
            + "</form>"
        )
        + card('<div id="list">' + empty_state("Loading...") + "</div>")
    )

    script = auth_fetch_helper("app_token") + """
if (!getToken()) location.href = '/login';

const list = document.getElementById('list');

function render(rows) {
  if (!rows.length) {
    list.innerHTML = '<div class="empty">Nothing here yet. Add your first one above.</div>';
    return;
  }
  // escapeHtml on every value that came from a user. Interpolating it raw is a stored
  // cross-site-scripting hole, and the checks store a hostile payload to prove it.
  list.innerHTML = rows.map(function (r) {
    return '<div class="list-row">'
         +   '<div><h3>' + escapeHtml(r.title) + '</h3>'
         +   '<small>' + escapeHtml(r.body || '') + '</small></div>'
         +   '<button class="btn btn-danger" data-id="' + escapeHtml(r.id) + '"'
         +   ' aria-label="Delete ' + escapeHtml(r.title) + '">Delete</button>'
         + '</div>';
  }).join('');

  list.querySelectorAll('button[data-id]').forEach(function (btn) {
    btn.onclick = async function () {
      try {
        await api('/api/notes/' + btn.dataset.id, { method: 'DELETE' });
        load();
      } catch (err) { showMessage('msg', err.message, 'err'); }
    };
  });
}

async function load() {
  try {
    render(await api('/api/notes'));
  } catch (err) {
    // An expired session is not an error to display - it is a redirect.
    if (/sign in|no longer valid/i.test(err.message)) { clearToken(); location.href = '/login'; }
    else list.innerHTML = '<div class="empty">' + escapeHtml(err.message) + '</div>';
  }
}

document.getElementById('new-note').addEventListener('submit', async function (e) {
  e.preventDefault();
  clearMessage('msg');
  const title = document.getElementById('title').value.trim();
  if (!title) { showMessage('msg', 'Give the note a title.', 'err'); return; }
  try {
    await api('/api/notes', {
      method: 'POST',
      body: JSON.stringify({ title: title, body: document.getElementById('body').value })
    });
    showMessage('msg', 'Saved.', 'ok');
    e.target.reset();
    load();
  } catch (err) { showMessage('msg', err.message, 'err'); }
});

load();
"""
    return page("Your notes", body, script=script, brand="Notebook")
