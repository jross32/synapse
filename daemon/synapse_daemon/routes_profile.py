"""REST routes for the optional Synapse account/Profile hub."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .api_versions import event_name
from .auth import AuthManager, require_token
from .errors import invalid
from .profile import ProfileConfigUpdate, ProfileManager


class ProfileSignInRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class ProfileSignUpRequest(ProfileSignInRequest):
    display_name: str | None = None


class FavoriteRequest(BaseModel):
    favorite: bool | None = None


class AuthStartResponse(BaseModel):
    url: str


def _callback_page(*, ok: bool, title: str, message: str) -> HTMLResponse:
    tone = "#22c55e" if ok else "#ef4444"
    body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #07110c;
        --panel: rgba(13, 28, 20, 0.96);
        --border: rgba(57, 94, 73, 0.8);
        --text: #e6f4ec;
        --muted: #9ec6ad;
        --accent: {tone};
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at top, rgba(34, 197, 94, 0.12), transparent 44%),
          linear-gradient(180deg, #020705 0%, var(--bg) 100%);
        color: var(--text);
        font-family: "Segoe UI", system-ui, sans-serif;
      }}
      .panel {{
        width: min(92vw, 460px);
        border: 1px solid var(--border);
        border-radius: 28px;
        padding: 28px;
        background: var(--panel);
        box-shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
      }}
      .badge {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: var(--muted);
      }}
      .dot {{
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: var(--accent);
        box-shadow: 0 0 20px color-mix(in srgb, var(--accent) 72%, transparent);
      }}
      h1 {{
        margin: 18px 0 8px;
        font-size: 28px;
        line-height: 1.1;
      }}
      p {{
        margin: 0;
        color: var(--muted);
        line-height: 1.55;
      }}
      .hint {{
        margin-top: 18px;
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    <section class="panel">
      <div class="badge"><span class="dot"></span>Synapse profile</div>
      <h1>{escape(title)}</h1>
      <p>{escape(message)}</p>
      <p class="hint">You can close this tab and return to Synapse.</p>
    </section>
    <script>
      setTimeout(() => {{
        try {{ window.close(); }} catch (err) {{}}
      }}, 1200);
    </script>
  </body>
</html>"""
    return HTMLResponse(body)


async def _publish_profile_updated(request: Request, manager: ProfileManager, reason: str) -> None:
    summary = manager.summary(refresh_remote=False).model_dump(mode="json")
    await request.app.state.bus.publish(
        event_name("profile", "updated"),
        {"reason": reason, "profile": summary},
    )
    await request.app.state.bus.publish(
        event_name("profile", "sync.updated"),
        {
            "reason": reason,
            "signed_in": summary["signed_in"],
            "sync_status": summary["sync_status"],
            "last_sync_at": summary["last_sync_at"],
            "last_sync_error": summary["last_sync_error"],
        },
    )


async def _publish_service_updated(request: Request, connection: dict, reason: str) -> None:
    await request.app.state.bus.publish(
        event_name("service_connection", "updated"),
        {"reason": reason, "connection": connection},
    )


def build_profile_router(storage, auth: AuthManager, manager: ProfileManager) -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])
    guard = Depends(require_token(auth))

    @router.get("", response_model=None, dependencies=[guard])
    async def get_profile() -> dict:
        return manager.summary().model_dump(mode="json")

    @router.patch("", response_model=None, dependencies=[guard])
    async def update_profile(payload: ProfileConfigUpdate, request: Request) -> dict:
        summary = manager.configure(payload)
        await _publish_profile_updated(request, manager, "config-updated")
        return summary.model_dump(mode="json")

    @router.post("/signup", response_model=None, dependencies=[guard])
    async def sign_up(payload: ProfileSignUpRequest, request: Request) -> dict:
        summary, notice = manager.sign_up_password(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
        await _publish_profile_updated(request, manager, "signed-up")
        return {"profile": summary.model_dump(mode="json"), "notice": notice}

    @router.post("/signin", response_model=None, dependencies=[guard])
    async def sign_in(payload: ProfileSignInRequest, request: Request) -> dict:
        summary = manager.sign_in_password(email=payload.email, password=payload.password)
        await _publish_profile_updated(request, manager, "signed-in")
        return summary.model_dump(mode="json")

    @router.post("/auth/start/{provider}", response_model=AuthStartResponse, dependencies=[guard])
    async def start_auth(provider: str, request: Request) -> AuthStartResponse:
        redirect_to = str(request.url_for("profile_auth_callback"))
        return AuthStartResponse(url=manager.start_oauth(provider=provider, redirect_to=redirect_to))

    @router.get("/auth/callback", response_model=None, name="profile_auth_callback")
    async def auth_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ):
        if error:
            return _callback_page(
                ok=False,
                title="Could not connect the Synapse account",
                message=error_description or error,
            )
        if not code or not state:
            return _callback_page(
                ok=False,
                title="Could not finish sign-in",
                message="The provider did not return the data Synapse expected.",
            )
        try:
            summary = manager.complete_oauth(code=code, state=state)
        except Exception as exc:
            return _callback_page(
                ok=False,
                title="Could not finish sign-in",
                message=str(exc),
            )
        await _publish_profile_updated(request, manager, "oauth-callback")
        return _callback_page(
            ok=True,
            title="Synapse account connected",
            message=f"Signed in as {summary.display_name or summary.email or 'your account'}.",
        )

    @router.post("/signout", response_model=None, dependencies=[guard])
    async def sign_out(request: Request) -> dict:
        summary = manager.sign_out()
        await _publish_profile_updated(request, manager, "signed-out")
        return summary.model_dump(mode="json")

    @router.get("/catalog-state", response_model=None, dependencies=[guard])
    async def catalog_state() -> dict:
        return manager.catalog_state().model_dump(mode="json")

    @router.post("/favorites/{kind}/{item_id}", response_model=None, dependencies=[guard])
    async def favorite_item(kind: str, item_id: str, payload: FavoriteRequest, request: Request) -> dict:
        if kind not in {"tool", "quick-action"}:
            raise invalid("profile", "kind must be 'tool' or 'quick-action'.")
        item = manager.set_favorite(kind=kind, item_id=item_id, favorite=payload.favorite)
        await _publish_profile_updated(request, manager, "favorite-updated")
        return item.model_dump(mode="json")

    @router.get("/service-connections", response_model=None, dependencies=[guard])
    async def list_services() -> dict:
        return {
            "connections": [
                connection.model_dump(mode="json")
                for connection in manager.list_service_connections()
            ]
        }

    @router.post("/service-connections/{provider}/connect", response_model=None, dependencies=[guard])
    async def connect_service(provider: str, request: Request) -> dict:
        connection = manager.connect_service(provider=provider)
        payload = connection.model_dump(mode="json")
        await _publish_service_updated(request, payload, "connected")
        await _publish_profile_updated(request, manager, "service-connected")
        return payload

    @router.post("/service-connections/{provider}/verify", response_model=None, dependencies=[guard])
    async def verify_service(provider: str, request: Request) -> dict:
        connection = manager.verify_service(provider=provider)
        payload = connection.model_dump(mode="json")
        await _publish_service_updated(request, payload, "verified")
        await _publish_profile_updated(request, manager, "service-verified")
        return payload

    @router.delete("/service-connections/{connection_id}", status_code=204, dependencies=[guard])
    async def delete_service(connection_id: str, request: Request) -> None:
        manager.delete_service_connection(connection_id)
        await _publish_service_updated(request, {"id": connection_id}, "deleted")
        await _publish_profile_updated(request, manager, "service-deleted")

    @router.get("/hosts", response_model=None, dependencies=[guard])
    async def list_hosts() -> dict:
        return {"hosts": [host.model_dump(mode="json") for host in manager.list_hosts()]}

    return router
