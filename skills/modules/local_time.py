"""Answer direct Italian clock queries using the configured household timezone."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo

from shared.protocol.memory import MemoryRequirement
from shared.protocol.skills import SkillMatch


# STT may include the wake phrase in an otherwise complete clock question.
# Keep the entire match anchored so alarms and time-dependent actions pass through.
_CLOCK_QUESTION = re.compile(
    r"(?:(?:(?:ehi|ei|hei|hey|e)\s*(?:nira|nyra|mira)|enira|e in iran?|nira)\s+)?"
    r"(?:(?:mi (?:dici|diresti)|dimmi|puoi dirmi)\s+)?"
    r"(?:che ore sono|che ora è|che ora e|l ora(?: attuale)?|l orario attuale)"
    r"(?: (?:adesso|ora|per favore))?"
)


class LocalTimeSkill:
    name = "local_time"
    priority = 101

    def __init__(self, timezone_name):
        self.zone = ZoneInfo(timezone_name)

    def matches(self, request):
        text = " ".join(re.sub(r"[^\w]+", " ", request.text.casefold()).split())
        return request.language.split("-")[0].lower() == "it" and bool(_CLOCK_QUESTION.fullmatch(text))

    def match(self, request):
        return SkillMatch(matched=True, skill_name=self.name, token=self.name,
                          memory_requirement=MemoryRequirement.NONE)

    def execute(self, request):
        now = datetime.now(self.zone)
        prefix = "È l’una" if now.hour == 1 else f"Sono le {now.hour}"
        return f"{prefix} e {now.minute:02d}." if now.minute else f"{prefix} in punto."
