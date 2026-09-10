from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from router.api.enrollments import require_auth
from router.skills_client import InvalidSkillsResponse, SkillsUnavailable


def _safe_skill(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    priority = item.get("priority")
    if not isinstance(name, str):
        return None
    return {
        "name": name,
        "priority": priority if isinstance(priority, int) else None,
        "enabled": bool(item.get("enabled", True)),
    }


def _safe_job(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    job_id = item.get("job_id")
    status = item.get("status")
    if not isinstance(job_id, str) or not isinstance(status, str):
        return None
    allowed = (
        "job_id",
        "status",
        "created_at",
        "execute_at",
        "started_at",
        "finished_at",
        "delay_seconds",
        "error",
        "request_id",
        "origin_request_id",
        "created_trace_id",
    )
    return {key: item.get(key) for key in allowed}


class SkillsAdminFacade:
    """Router-owned, secret-free diagnostics facade for Skills and jobs."""

    def __init__(self, skills_client=None, ha_capability=None) -> None:
        self.skills_client = skills_client
        self.ha_capability = ha_capability

    async def snapshot(self) -> dict[str, Any]:
        capability = {
            "home_assistant": {
                "configured": self.ha_capability is not None,
                "operations": [
                    "resolve",
                    "execute",
                    "automation.create",
                    "automation.update",
                    "automation.delete",
                ] if self.ha_capability is not None else [],
            }
        }

        if self.skills_client is None:
            return {
                "service": {
                    "configured": False,
                    "ready": False,
                    "status": "unconfigured",
                    "error": None,
                },
                "skills": [],
                "jobs": [],
                "capabilities": capability,
            }

        try:
            data = await self.skills_client.diagnostics()
        except (SkillsUnavailable, InvalidSkillsResponse) as exc:
            return {
                "service": {
                    "configured": True,
                    "ready": False,
                    "status": "unavailable",
                    "error": type(exc).__name__,
                },
                "skills": [],
                "jobs": [],
                "capabilities": capability,
            }

        health = data.get("health") if isinstance(data, dict) else {}
        ready = bool(data.get("ready")) if isinstance(data, dict) else False
        raw_skills = data.get("skills") if isinstance(data, dict) else []
        raw_jobs = data.get("jobs") if isinstance(data, dict) else []

        skills = [
            safe
            for safe in (_safe_skill(item) for item in (raw_skills or []))
            if safe is not None
        ]
        jobs = [
            safe
            for safe in (_safe_job(item) for item in (raw_jobs or []))
            if safe is not None
        ]
        return {
            "service": {
                "configured": True,
                "ready": ready,
                "status": (
                    health.get("status", "unknown")
                    if isinstance(health, dict)
                    else "unknown"
                ),
                "error": None,
            },
            "skills": skills,
            "jobs": jobs,
            "capabilities": capability,
        }


router = APIRouter(prefix="/v1/admin")


@router.get("/skills")
async def skills_diagnostics(request: Request):
    require_auth(request)
    facade = getattr(request.app.state, "skills_admin", None)
    if facade is None:
        raise HTTPException(status_code=503, detail="Skills diagnostics unavailable")
    return await facade.snapshot()
