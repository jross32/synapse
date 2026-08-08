"""Conversations with a local model: storage, lazy engine start, and streamed replies.

Design constraints that come from the user's machine rather than from taste:

* **Nothing runs until it is wanted.** Ollama is not started, and no model is loaded, just
  because Synapse is open. A resident 5 GB model on a 16 GB laptop is a real cost to
  everything else the person is doing. The engine starts on the first prompt.
* **The wait is shown, not hidden.** A cold 7B load takes tens of seconds. The stream emits
  distinct ``engine_starting`` / ``model_loading`` / ``ready`` phases with elapsed time, so
  the UI can show what is actually happening instead of a spinner that implies nothing is.
* **Failures are loud.** If the engine will not start or the model will not load, the stream
  says which, and why, in words a person can act on.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

from . import ollama_client
from .local_agent import (
    MAX_TOOL_CHARS,
    MODE_TOOLS,
    MUTATING_TOOLS,
    TOOL_REQUIRED_ARGS,
    PermissionMode,
    missing_args,
    Workspace,
    build_tools,
    web_fetch,
    web_search,
)

OLLAMA_URL = "http://127.0.0.1:11434"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------- models


class ChatMessage(BaseModel):
    id: str
    chat_id: str
    seq: int
    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tokens_out: int | None = None
    duration_s: float | None = None
    created_at: str


class Chat(BaseModel):
    id: str
    title: str
    model: str
    mode: str = PermissionMode.AUTO.value
    workspace: str | None = None
    project_id: str | None = None
    created_at: str
    updated_at: str
    archived_at: str | None = None
    message_count: int = 0


# ---------------------------------------------------------------- storage


def title_from_prompt(prompt: str) -> str:
    """Name a chat after its opening line, the way people name things themselves.

    Kept short and stripped of leading command words so the sidebar reads as a list of
    subjects rather than a list of "Please can you..." fragments.
    """
    text = " ".join(prompt.strip().split())
    for lead in ("please ", "can you ", "could you ", "i want you to ", "i need you to ",
                 "hey ", "hi "):
        if text.lower().startswith(lead):
            text = text[len(lead):]
    text = text[:1].upper() + text[1:] if text else "New chat"
    if len(text) > 60:
        cut = text[:60].rsplit(" ", 1)[0]
        text = cut + "..."
    return text or "New chat"


def create_chat(conn: sqlite3.Connection, *, model: str, first_prompt: str = "",
                mode: str = PermissionMode.AUTO.value, workspace: str | None = None,
                project_id: str | None = None, title: str | None = None) -> Chat:
    now = _now()
    chat = Chat(id=_uid(), title=title or title_from_prompt(first_prompt) if (title or first_prompt)
                else "New chat",
                model=model, mode=mode, workspace=workspace, project_id=project_id,
                created_at=now, updated_at=now)
    conn.execute(
        "INSERT INTO local_chats (id, title, model, mode, workspace, project_id, "
        "created_at, updated_at, metadata_json) VALUES (?,?,?,?,?,?,?,?,'{}')",
        (chat.id, chat.title, chat.model, chat.mode, chat.workspace, chat.project_id,
         chat.created_at, chat.updated_at),
    )
    conn.commit()
    return chat


def list_chats(conn: sqlite3.Connection, *, include_archived: bool = False,
               limit: int = 100) -> list[Chat]:
    sql = ("SELECT c.*, (SELECT COUNT(*) FROM local_chat_messages m WHERE m.chat_id=c.id) "
           "AS message_count FROM local_chats c ")
    if not include_archived:
        sql += "WHERE c.archived_at IS NULL "
    sql += "ORDER BY c.updated_at DESC LIMIT ?"
    rows = conn.execute(sql, (limit,)).fetchall()
    return [Chat(id=r["id"], title=r["title"], model=r["model"], mode=r["mode"],
                 workspace=r["workspace"], project_id=r["project_id"],
                 created_at=r["created_at"], updated_at=r["updated_at"],
                 archived_at=r["archived_at"], message_count=r["message_count"])
            for r in rows]


def get_chat(conn: sqlite3.Connection, chat_id: str) -> Chat | None:
    r = conn.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM local_chat_messages m WHERE m.chat_id=c.id) "
        "AS message_count FROM local_chats c WHERE c.id=?", (chat_id,)).fetchone()
    if not r:
        return None
    return Chat(id=r["id"], title=r["title"], model=r["model"], mode=r["mode"],
                workspace=r["workspace"], project_id=r["project_id"],
                created_at=r["created_at"], updated_at=r["updated_at"],
                archived_at=r["archived_at"], message_count=r["message_count"])


def get_messages(conn: sqlite3.Connection, chat_id: str) -> list[ChatMessage]:
    rows = conn.execute(
        "SELECT * FROM local_chat_messages WHERE chat_id=? ORDER BY seq", (chat_id,)).fetchall()
    return [ChatMessage(id=r["id"], chat_id=r["chat_id"], seq=r["seq"], role=r["role"],
                        content=r["content"],
                        tool_calls=json.loads(r["tool_calls_json"] or "[]"),
                        tokens_out=r["tokens_out"], duration_s=r["duration_s"],
                        created_at=r["created_at"])
            for r in rows]


def append_message(conn: sqlite3.Connection, chat_id: str, role: str, content: str = "",
                   tool_calls: list[dict] | None = None, tokens_out: int | None = None,
                   duration_s: float | None = None) -> ChatMessage:
    row = conn.execute("SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM local_chat_messages "
                       "WHERE chat_id=?", (chat_id,)).fetchone()
    msg = ChatMessage(id=_uid(), chat_id=chat_id, seq=row["n"], role=role, content=content,
                      tool_calls=tool_calls or [], tokens_out=tokens_out,
                      duration_s=duration_s, created_at=_now())
    conn.execute(
        "INSERT INTO local_chat_messages (id, chat_id, seq, role, content, tool_calls_json, "
        "tokens_out, duration_s, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (msg.id, msg.chat_id, msg.seq, msg.role, msg.content,
         json.dumps(msg.tool_calls) if msg.tool_calls else None,
         msg.tokens_out, msg.duration_s, msg.created_at))
    conn.execute("UPDATE local_chats SET updated_at=? WHERE id=?", (msg.created_at, chat_id))
    conn.commit()
    return msg


def rename_chat(conn: sqlite3.Connection, chat_id: str, title: str) -> None:
    conn.execute("UPDATE local_chats SET title=?, updated_at=? WHERE id=?",
                 (title.strip()[:120] or "New chat", _now(), chat_id))
    conn.commit()


def archive_chat(conn: sqlite3.Connection, chat_id: str) -> None:
    conn.execute("UPDATE local_chats SET archived_at=?, updated_at=? WHERE id=?",
                 (_now(), _now(), chat_id))
    conn.commit()


def delete_chat(conn: sqlite3.Connection, chat_id: str) -> None:
    conn.execute("DELETE FROM local_chat_messages WHERE chat_id=?", (chat_id,))
    conn.execute("DELETE FROM local_chats WHERE id=?", (chat_id,))
    conn.commit()


# ---------------------------------------------------------------- engine readiness


async def _model_resident(model: str) -> bool:
    """Is this model already loaded in memory? Determines whether to warn about a wait."""
    def _do() -> bool:
        try:
            with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return False
        return any(m.get("name") == model or m.get("model") == model
                   for m in data.get("models", []))
    return await asyncio.to_thread(_do)


async def ensure_ready(model: str) -> AsyncIterator[dict[str, Any]]:
    """Bring the engine and model up, narrating each phase.

    Yields status events so the caller can show real progress. Ollama does not report a
    load percentage for chat requests, so rather than fake one this reports the phase and
    the elapsed seconds, which is honest and still tells the user it is working.
    """
    if not ollama_client.is_installed():
        yield {"type": "error", "phase": "engine",
               "message": "Ollama isn't installed on this machine, so local models can't run.",
               "remedy": "Install it from ollama.com, then reopen this chat."}
        return

    if not await ollama_client.server_up():
        yield {"type": "status", "phase": "engine_starting",
               "message": "Starting the local model engine..."}
        started = await asyncio.to_thread(ollama_client.start_server)
        if not started:
            yield {"type": "error", "phase": "engine",
                   "message": "The local model engine failed to start.",
                   "remedy": "Try running `ollama serve` in a terminal to see why."}
            return
        t0 = time.time()
        while time.time() - t0 < 30:
            if await ollama_client.server_up():
                break
            await asyncio.sleep(0.5)
        else:
            yield {"type": "error", "phase": "engine",
                   "message": "The engine started but never became reachable on port 11434.",
                   "remedy": "Check whether something else is using that port."}
            return
        yield {"type": "status", "phase": "engine_ready",
               "message": "Engine running.", "elapsed_s": round(time.time() - t0, 1)}

    if not await _model_resident(model):
        yield {"type": "status", "phase": "model_loading",
               "message": f"Loading {model} into memory. The first reply after a cold start "
                          f"takes a little longer.",
               "model": model}


# ---------------------------------------------------------------- streamed reply


async def stream_reply(
    conn: sqlite3.Connection,
    chat: Chat,
    prompt: str,
    *,
    allow_web: bool = True,
    max_tool_rounds: int = 6,
    num_ctx: int = 8192,
) -> AsyncIterator[dict[str, Any]]:
    """Run one user turn, streaming phases, tokens and tool activity as they happen."""
    mode = PermissionMode(chat.mode)
    allowed = MODE_TOOLS[mode]
    ws_root = chat.workspace or str(_default_workspace())
    ws = Workspace(ws_root, allow_shell="run_command" in allowed,
                   allow_destructive=(mode is PermissionMode.BYPASS))
    tools = build_tools(mode, allow_web)

    handlers = {"read_file": ws.read_file, "write_file": ws.write_file,
                "list_dir": ws.list_dir, "run_command": ws.run_command,
                "web_search": web_search, "web_fetch": web_fetch}

    append_message(conn, chat.id, "user", prompt)
    yield {"type": "user_saved"}

    # Register in Live View. A local model driving this machine is an AI at work like any
    # other, and the operator should see it there rather than have it run invisibly. The
    # resume_key ties every turn of one conversation to a single session instead of minting
    # a new number per message.
    session_id: str | None = None
    try:
        from . import coordination  # local import: chat must not hard-depend on it

        session = coordination.register_session(conn, coordination.AgentSessionRegister(
            project_id=chat.project_id,
            runtime_id="ollama",
            agent_label=f"Local · {chat.model}",
            task=prompt[:200],
            resume_key=f"local-chat:{chat.id}",
        ))
        session_id = session.id
    except Exception:  # noqa: BLE001 -- visibility is a nicety; never fail a chat over it
        session_id = None

    def _beat(intent: str) -> None:
        if not session_id:
            return
        try:
            from . import coordination  # noqa: PLC0415

            coordination.heartbeat_session(
                conn, session_id, coordination.AgentSessionHeartbeat(last_intent=intent[:8000]))
        except Exception:  # noqa: BLE001
            pass

    async for ev in ensure_ready(chat.model):
        yield ev
        if ev.get("type") == "error":
            return

    history = get_messages(conn, chat.id)
    messages: list[dict[str, Any]] = [{
        "role": "system",
        # State the workspace explicitly. Without it the model invents absolute paths like
        # /home/user/workspace/x.py, gets refused by the containment check, and then loops
        # inventing different absolute paths instead of correcting the shape.
        "content": (
            "You are a helpful coding assistant running locally on the user's own machine.\n"
            f"Your workspace is: {ws.root}\n"
            "All file paths you pass to tools MUST be relative to that workspace root - "
            "for example 'greet.py' or 'src/app.js'. Never pass an absolute path.\n"
            "Use the tools to read and change real files rather than guessing what they "
            "contain. Be concise and concrete."
        ),
    }]
    for m in history:
        if m.role in ("user", "assistant") and m.content:
            messages.append({"role": m.role, "content": m.content})

    total_tokens = 0
    started = time.time()
    first_token_seen = False

    for _round in range(max_tool_rounds):
        payload = {"model": chat.model, "messages": messages, "stream": True,
                   "options": {"temperature": 0.3, "num_ctx": num_ctx}}
        if tools:
            payload["tools"] = tools

        queue: asyncio.Queue = asyncio.Queue()

        def _pump() -> None:
            try:
                req = urllib.request.Request(
                    f"{OLLAMA_URL}/api/chat",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=600) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8").strip()
                        if line:
                            queue.put_nowait(json.loads(line))
            except Exception as exc:  # noqa: BLE001
                queue.put_nowait({"__error__": f"{type(exc).__name__}: {exc}"})
            finally:
                queue.put_nowait({"__done__": True})

        task = asyncio.get_running_loop().run_in_executor(None, _pump)
        assistant_text = ""
        tool_calls: list[dict] = []
        err: str | None = None

        while True:
            chunk = await queue.get()
            if chunk.get("__done__"):
                break
            if chunk.get("__error__"):
                err = chunk["__error__"]
                break
            msg = chunk.get("message") or {}
            if not first_token_seen:
                first_token_seen = True
                yield {"type": "status", "phase": "ready", "message": "Connected.",
                       "elapsed_s": round(time.time() - started, 1)}
            piece = msg.get("content") or ""
            if piece:
                assistant_text += piece
                yield {"type": "token", "text": piece}
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
            if chunk.get("done"):
                total_tokens += chunk.get("eval_count") or 0
        await task

        if err:
            yield {"type": "error", "phase": "model",
                   "message": f"The model stopped unexpectedly: {err}"}
            append_message(conn, chat.id, "assistant", assistant_text or "",
                           tokens_out=total_tokens)
            return

        if not tool_calls:
            append_message(conn, chat.id, "assistant", assistant_text,
                           tokens_out=total_tokens,
                           duration_s=round(time.time() - started, 2))
            _beat("replied")
            yield {"type": "done", "tokens_out": total_tokens,
                   "duration_s": round(time.time() - started, 2)}
            return

        messages.append({"role": "assistant", "content": assistant_text,
                         "tool_calls": tool_calls})
        executed: list[dict] = []
        for call in tool_calls:
            spec = call.get("function") or {}
            name = spec.get("name") or ""
            args = spec.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            args = args if isinstance(args, dict) else {}

            yield {"type": "tool_start", "name": name, "arguments": args}
            _beat(f"{name} {list(args.values())[:1]}")

            if name not in allowed or name not in handlers:
                result = (f"ERROR: {name} is not available in {mode.value} mode. "
                          f"Available: {', '.join(sorted(allowed))}.")
            elif mode is PermissionMode.MANUAL and name in MUTATING_TOOLS:
                result = ("ERROR: manual mode - this action needs the user's approval "
                          "before it can run.")
            elif missing_args(name, args):
                need = ", ".join(missing_args(name, args))
                result = (f"ERROR: {name} is missing required argument(s): {need}. "
                          f"Call it again with all of: "
                          f"{', '.join(TOOL_REQUIRED_ARGS.get(name, [])) or '(none)'}.")
            else:
                try:
                    result = await asyncio.to_thread(lambda: handlers[name](**args))
                except Exception as exc:  # noqa: BLE001
                    result = f"ERROR: {type(exc).__name__}: {exc}"
            if len(result) > MAX_TOOL_CHARS:
                result = result[:MAX_TOOL_CHARS] + "\n...[truncated]"

            executed.append({"name": name, "arguments": args, "result": result})
            messages.append({"role": "tool", "content": result})
            yield {"type": "tool_end", "name": name, "result": result}

        append_message(conn, chat.id, "assistant", assistant_text, tool_calls=executed)

    yield {"type": "error", "phase": "model",
           "message": f"Stopped after {max_tool_rounds} rounds of tool use without a final "
                      "answer."}


def _default_workspace():
    from pathlib import Path
    p = Path.home() / ".synapse" / "local-chat-workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p
