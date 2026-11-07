"""Voice commands for source-scoped persistent audio jobs."""

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

from shared.protocol.skills import (
    SkillExecuteResponse,
    SkillOutcome,
    JobStatus,
    SkillMatch,
)
from skills.alert_parser import alert_kind, parse_alert, call_message


def management_command(text):
    text = " ".join(text.lower().strip(" .!?").split())
    match = re.fullmatch(
        r"(elenca|quali|annulla|cancella|ferma|stop|list|cancel)\s+(.*)", text
    )
    if not match:
        return None
    verb, target = match.groups()
    if not re.search(
        r"\b(timer|timers|sveglia|sveglie|alarm|alarms|chiamata|chiamate|call|calls|avvisi|alerts|job_[\w-]+)\b",
        target,
    ):
        return None
    action = (
        "list"
        if verb in ("elenca", "quali", "list")
        else "cancel" if verb in ("annulla", "cancella", "cancel") else "stop"
    )
    kind = (
        "timer"
        if "timer" in target
        else (
            "alarm"
            if re.search("svegli|alarm", target)
            else "call" if re.search("chiamat|call", target) else None
        )
    )
    job = re.search(r"job_[\w-]+", target)
    return action, kind, job.group() if job else None


class VoiceAlertsSkill:
    name = "voice_alerts"
    priority = 115

    def __init__(
        self, scheduler, *, timezone_name="Europe/Rome", max_seconds=60, now=None
    ):
        if not 1 <= max_seconds <= 60:
            raise ValueError("alert cap must be 1..60 seconds")
        self.scheduler = scheduler
        self.timezone_name = timezone_name
        self.max_seconds = max_seconds
        self.now = now or (lambda: datetime.now(timezone.utc))

    def matches(self, request):
        return bool(
            alert_kind(request.text)
            or management_command(request.text)
            or (request.pending_state or {}).get("kind") == "voice_alerts"
        )

    def match(self, request=None):
        return SkillMatch(matched=True, skill_name=self.name, token=self.name)

    def _response(self, request, text, *, clarify=False, result=None):
        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=(
                SkillOutcome.NEEDS_CLARIFICATION if clarify else SkillOutcome.HANDLED
            ),
            text=text,
            result=result,
            pending_state={"kind": "voice_alerts"} if clarify else None,
        )

    async def execute(self, request):
        it = request.language.lower().startswith("it")
        source = request.context.get("source_id")
        if not source:
            return self._response(
                request, "Da quale speaker?" if it else "Which speaker?", clarify=True
            )
        management = management_command(request.text)
        pending = request.pending_state or {}
        if (
            management is None
            and pending.get("kind") == "voice_alerts"
            and pending.get("action")
        ):
            candidates = pending.get("candidates", [])
            text = request.text.lower().strip()
            selected = next((job for job in candidates if job in text), None)
            ordinals = {
                "il primo": 0,
                "il secondo": 1,
                "the first": 0,
                "the second": 1,
                "1": 0,
                "2": 1,
            }
            index = ordinals.get(text)
            if selected is None and index is not None and index < len(candidates):
                selected = candidates[index]
            if selected is None:
                response = self._response(
                    request,
                    "Indica quale avviso." if it else "Specify which alert.",
                    clarify=True,
                )
                response.pending_state = pending
                return response
            management = (pending["action"], pending.get("alert_kind"), selected)
        if management:
            action, kind, job_id = management
            jobs = [
                j
                for j in self.scheduler.store.list()
                if j.payload.get("kind") == "voice_alert"
                and j.payload.get("source_id") == source
                and (kind is None or j.payload.get("alert_kind") == kind)
                and (job_id is None or j.job_id == job_id)
                and j.status in (JobStatus.SCHEDULED, JobStatus.RUNNING)
            ]
            jobs.sort(key=lambda j: (j.execute_at, j.created_at, j.job_id))
            if action == "list":
                names = {
                    "alarm": "Sveglia" if it else "Alarm",
                    "timer": "Timer",
                    "call": "Chiamata" if it else "Call",
                }
                labels = [
                    f"{index}. {names[j.payload['alert_kind']]} {'alle' if it else 'at'} {j.execute_at.astimezone(ZoneInfo(self.timezone_name)):%H:%M}"
                    for index, j in enumerate(jobs, 1)
                ]
                return self._response(
                    request,
                    (
                        "; ".join(labels)
                        if labels
                        else ("Nessun avviso attivo." if it else "No active alerts.")
                    ),
                    result={"jobs": [j.model_dump(mode="json") for j in jobs]},
                )
            jobs = [
                j
                for j in jobs
                if j.status
                == (JobStatus.SCHEDULED if action == "cancel" else JobStatus.RUNNING)
            ]
            if not jobs:
                return self._response(
                    request,
                    "Nessun avviso corrispondente." if it else "No matching alert.",
                )
            if len(jobs) > 1:
                response = self._response(
                    request,
                    (
                        "Quale avviso? Indica il suo identificativo o il primo/secondo."
                        if it
                        else "Which alert? Specify its ID or first/second."
                    ),
                    clarify=True,
                    result={"jobs": [j.job_id for j in jobs]},
                )
                response.pending_state = {
                    "kind": "voice_alerts",
                    "action": action,
                    "alert_kind": kind,
                    "candidates": [j.job_id for j in jobs],
                }
                return response
            result = await (
                self.scheduler.cancel_job(jobs[0].job_id)
                if action == "cancel"
                else self.scheduler.stop_job(jobs[0].job_id)
            )
            if action == "stop" and result.status != JobStatus.STOPPED:
                return self._response(
                    request,
                    (
                        "Arresto richiesto; attendo conferma dallo speaker."
                        if it
                        else "Stop requested; awaiting speaker confirmation."
                    ),
                    result={"job_id": result.job_id, "status": result.status.value},
                )
            return self._response(
                request,
                (
                    "Annullato."
                    if action == "cancel" and it
                    else (
                        "Fermato."
                        if it
                        else "Cancelled." if action == "cancel" else "Stopped."
                    )
                ),
                result={"job_id": result.job_id, "status": result.status.value},
            )
        text = request.text
        if (
            not alert_kind(text)
            and pending.get("alert_kind")
            and not pending.get("action")
        ):
            prefixes = {
                "alarm": "svegliami" if it else "wake me",
                "call": "chiamami" if it else "call me",
                "timer": "metti un timer" if it else "set a timer",
            }
            tail = text.strip()
            if not re.match(r"^(tra|fra|alle|di|in|at|for)\b", tail.lower()):
                tail = (
                    "di "
                    if pending["alert_kind"] == "timer" and it
                    else "tra " if it else "in "
                ) + tail
            text = prefixes[pending["alert_kind"]] + " " + tail
        try:
            parsed = parse_alert(text, request.language, self.now(), self.timezone_name)
        except (ValueError, OverflowError):
            response = self._response(
                request,
                (
                    "Specifica una durata positiva o un orario valido e non ambiguo."
                    if it
                    else "Specify a positive duration or a valid unambiguous time."
                ),
                clarify=True,
            )
            response.pending_state = {
                "kind": "voice_alerts",
                "alert_kind": alert_kind(text) or pending.get("alert_kind"),
            }
            return response
        identity = request.context.get("identity") or {}
        name = (
            identity.get("display_name")
            if identity.get("resolution_source") == "SPEAKER_IDENTIFICATION"
            else None
        )
        name = (
            " ".join(name.split()) if isinstance(name, str) and name.strip() else None
        )
        payload = {
            "kind": "voice_alert",
            "alert_kind": parsed.kind,
            "source_id": source,
            "language": request.language,
            "timezone": self.timezone_name,
            "duration_seconds": parsed.duration_seconds,
            "clock": parsed.clock,
            "name": name,
            "message": (
                call_message(parsed, request.language, name)
                if parsed.kind == "call"
                else None
            ),
            "max_seconds": self.max_seconds,
        }
        job = self.scheduler.schedule_alert(
            execute_at=parsed.execute_at,
            origin_request_id=request.correlation.origin_request_id
            or request.correlation.request_id,
            created_trace_id=request.correlation.trace_id,
            payload=payload,
        )
        local = parsed.execute_at.astimezone(ZoneInfo(self.timezone_name))
        return self._response(
            request,
            f"Impostato per le {local:%H:%M}." if it else f"Set for {local:%H:%M}.",
            result={"job_id": job.job_id, "execute_at": job.execute_at.isoformat()},
        )
