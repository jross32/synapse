"""Read-only, evidence-backed AI Workforce overview based on existing staff/squads."""
from __future__ import annotations

from collections import Counter
from typing import Any

from . import agent_squads, staff, thread_presence, coordination


def workforce_snapshot(conn) -> dict[str, Any]:
    members = staff.list_staff(conn)
    squads = agent_squads.list_squads(conn)
    work = []
    for squad in squads:
        for item in agent_squads.list_work_items(conn, squad.id):
            work.append({**item.model_dump(mode="json"), "project_id": squad.project_id,
                         "squad_name": squad.name})
    work.sort(key=lambda item: item["updated_at"], reverse=True)
    counts = Counter(item["status"] for item in work)
    agents = []
    for member in members:
        assignments = staff.list_recent_work_items(conn, member.id, limit=20)
        running = next((item for item in assignments if item["status"] == "running"), None)
        agents.append({"id": member.id, "name": member.display_name,
                       "handle": member.handle, "role": member.title,
                       "status": member.status.value, "status_line": member.status_line,
                       "avatar_asset_id": member.avatar_asset_id,
                       "assigned_project_ids": member.assigned_project_ids,
                       "authority_policy": member.authority_policy.value,
                       "current_task": running, "recent_work_count": len(assignments),
                       "completed_in_recent_work": sum(item["status"] == "completed" for item in assignments)})
    # Heartbeat-derived presence is separate from staff labels and historical work items.
    threads = thread_presence.list_threads(conn)
    sessions = coordination.list_all_sessions(conn)
    live_threads = [{"id": t.id, "title": t.title, "runtime_id": t.runtime_id,
                     "project_id": t.project_id, "status": t.display_status.value,
                     "stale": t.stale, "current_task": t.current_task,
                     "last_seen_at": t.last_seen_at.isoformat(),
                     "total_work_seconds": t.total_work_seconds}
                    for t in threads]
    live_sessions = [{"id": s.id, "agent_label": s.agent_label,
                      "runtime_id": s.runtime_id, "project_id": s.project_id,
                      "status": s.status.value, "stale": s.stale,
                      "task": s.task, "connection_level": s.connection_level,
                      "last_heartbeat_at": s.last_heartbeat_at.isoformat()}
                     for s in sessions if s.status.value != "gone"]
    return {"agents": agents, "tasks": work[:100], "threads": live_threads,
            "sessions": live_sessions, "presence": {
                "active_threads": sum(t["status"] == "active" and not t["stale"] for t in live_threads),
                "connected_sessions": sum(s["status"] == "active" and not s["stale"] for s in live_sessions),
                "stale_sessions": sum(s["stale"] for s in live_sessions),
            }, "metrics": {
        "agents_total": len(agents),
        "agents_working": sum(agent["status"] == "working" for agent in agents),
        "tasks_active": counts["running"],
        "tasks_queued": counts["queued"],
        "tasks_completed_recorded": counts["completed"],
        "tasks_blocked": counts["blocked"],
    }, "data_scope": "local_synapse_records", "live_device_presence": False,
       "note": "Staff status and task counts reflect persisted records. Thread/session presence is heartbeat-derived; device uptime is not verified."}
