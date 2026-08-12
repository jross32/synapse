"""HTML partials for generated apps: correct markup the model cannot get wrong.

The build-off produced pages with zero ``<label>`` elements, no ``autocomplete`` hints, no
focus styles and no tap-target sizing. The model was not incapable — it was asked to invent
markup, and invented the minimum that looked right.

So the accessible details live here instead. ``field()`` cannot emit an input without a
matching label, because the label is not optional in the function that builds it. A model
that calls these gets correct markup whether or not it knows why the markup matters, and a
model that ignores them fails the checks in ``webcheck``.

Everything renders plain HTML against ``ui_kit/kit.css``. No framework, no build step: a
generated app still has to run with nothing but Python installed.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

KIT_DIR = Path(__file__).parent / "ui_kit"


def kit_css() -> str:
    """The house stylesheet, inlined into every page so an app is a single artefact."""
    return (KIT_DIR / "kit.css").read_text(encoding="utf-8")


def esc(value: object) -> str:
    """Escape for HTML text and attributes.

    Used by every partial, and exported because generated client-side code needs the same
    guarantee. Arm B interpolated a record name straight into ``innerHTML`` and shipped a
    stored XSS hole; nothing here can do that by accident.
    """
    return html.escape(str(value), quote=True)


def field(
    name: str,
    label: str,
    *,
    kind: str = "text",
    required: bool = True,
    autocomplete: str = "",
    hint: str = "",
    attrs: str = "",
) -> str:
    """One labelled form control.

    The label is a required argument rather than an option, which is the whole point: there
    is no call that produces an unlabelled input. ``for``/``id`` are wired together so screen
    readers and clicking the label both work.
    """
    ident = esc(name)
    auto = f' autocomplete="{esc(autocomplete)}"' if autocomplete else ""
    req = " required" if required else ""
    hint_html = f'<p class="field-hint" id="{ident}-hint">{esc(hint)}</p>' if hint else ""
    described = f' aria-describedby="{ident}-hint"' if hint else ""
    return (
        f'<div class="field">'
        f'<label for="{ident}">{esc(label)}</label>'
        f'<input id="{ident}" name="{ident}" type="{esc(kind)}"{auto}{req}{described} {attrs}>'
        f"{hint_html}"
        f"</div>"
    )


def button(text: str, *, kind: str = "submit", variant: str = "", block: bool = True,
           attrs: str = "") -> str:
    classes = " ".join(c for c in ("btn", variant, "btn-block" if block else "") if c)
    return f'<button type="{esc(kind)}" class="{classes}" {attrs}>{esc(text)}</button>'


def link_button(text: str, href: str, *, variant: str = "btn-secondary") -> str:
    return f'<a class="btn {variant}" href="{esc(href)}">{esc(text)}</a>'


def message_slot(ident: str = "msg") -> str:
    """An empty, hidden region for errors and confirmations.

    Generated pages routinely have nowhere to show a failure and end up silently doing
    nothing. Giving them a slot by default means the failure path exists before it is needed.
    """
    return f'<div id="{esc(ident)}" class="msg" role="status" aria-live="polite"></div>'


def empty_state(text: str) -> str:
    return f'<div class="empty">{esc(text)}</div>'


def card(inner: str) -> str:
    return f'<div class="card">{inner}</div>'


def page(title: str, body: str, *, script: str = "", brand: str = "App",
         nav: str = "") -> str:
    """A complete document: viewport meta, inlined kit, top bar, main region.

    ``script`` is inserted verbatim as module-free JS. It is generated code, not user input,
    so it is not escaped — but anything it renders must go through ``escapeHtml`` below.
    """
    brand_html = esc(brand)
    if "<em>" not in brand_html and len(brand) > 4:
        # Colour the tail of the name, so the brand reads as designed rather than as plain text.
        brand_html = f"{esc(brand[:-4])}<em>{esc(brand[-4:])}</em>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{kit_css()}</style>
</head>
<body>
<header class="topbar"><div class="brand">{brand_html}</div><div>{nav}</div></header>
<main class="wrap">{body}</main>
<script>{CLIENT_HELPERS}
{script}</script>
</body>
</html>"""


# Shipped with every page. `escapeHtml` exists so client-side rendering has a safe default
# available without the model having to write one — the omission that produced the XSS.
CLIENT_HELPERS = """
function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function showMessage(id, text, kind) {
  var el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'msg ' + (kind || 'err');
}
function clearMessage(id) {
  var el = document.getElementById(id);
  if (el) { el.textContent = ''; el.className = 'msg'; }
}
"""


def auth_fetch_helper(token_key: str = "app_token") -> str:
    """Client-side API helper with the auth header and error handling already correct."""
    return f"""
var TOKEN_KEY = {json.dumps(token_key)};
function getToken() {{ return localStorage.getItem(TOKEN_KEY); }}
function setToken(t) {{ localStorage.setItem(TOKEN_KEY, t); }}
function clearToken() {{ localStorage.removeItem(TOKEN_KEY); }}
async function api(path, options) {{
  var o = options || {{}};
  o.headers = Object.assign({{'Content-Type': 'application/json'}}, o.headers || {{}});
  var t = getToken();
  if (t) o.headers['Authorization'] = 'Bearer ' + t;
  var res = await fetch(path, o);
  var data = null;
  try {{ data = await res.json(); }} catch (e) {{ }}
  if (!res.ok) {{
    throw new Error((data && (data.detail || data.error)) || ('Request failed (' + res.status + ')'));
  }}
  return data;
}}
"""
