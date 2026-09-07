from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
import sqlite3
from threading import RLock
import uuid
from typing import Protocol, Sequence


class PhraseLength(str, Enum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"


class EnrollmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


@dataclass(frozen=True)
class EnrollmentPhrase:
    text: str
    language: str
    length_class: PhraseLength


@dataclass(frozen=True)
class EnrollmentSession:
    session_id: str
    profile_user_id: str
    source_id: str
    language: str
    target_count: int
    accepted_sample_ids: tuple[str, ...]
    phrases: tuple[EnrollmentPhrase, ...]
    status: EnrollmentStatus
    termination_reason: str | None = None
    last_reason_code: str | None = None

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_sample_ids)

    @property
    def current_phrase(self) -> EnrollmentPhrase | None:
        if self.status is not EnrollmentStatus.ACTIVE:
            return None
        return self.phrases[self.accepted_count]


class EnrollmentNotFound(KeyError):
    pass


class EnrollmentConflict(RuntimeError):
    pass


class PhraseGenerator(Protocol):
    def generate(self, language: str, target_count: int) -> Sequence[EnrollmentPhrase]: ...


_FALLBACK = {
    "it": {
        PhraseLength.SHORT: ("La luce è accesa.", "Oggi resto a casa."),
        PhraseLength.MEDIUM: ("Questa mattina il cielo sopra casa è molto limpido.", "Vorrei ascoltare della musica mentre preparo la cena."),
        PhraseLength.LONG: ("Domani controllerò il calendario prima di organizzare tutti gli impegni della giornata.", "Quando torno a casa preferisco abbassare le luci e ascoltare qualcosa di tranquillo."),
    },
    "en": {
        PhraseLength.SHORT: ("The light is on.", "Today I am staying home."),
        PhraseLength.MEDIUM: ("The sky above the house is very clear this morning.", "I would like some music while I prepare dinner."),
        PhraseLength.LONG: ("Tomorrow I will check the calendar before arranging all the activities for the day.", "When I come home I prefer to dim the lights and listen to something quiet."),
    },
}


def deterministic_phrase_plan(language: str, target_count: int) -> tuple[EnrollmentPhrase, ...]:
    locale = language.strip()
    base = locale.split("-", 1)[0].lower()
    catalog = _FALLBACK.get(base, _FALLBACK["en"])
    order = (PhraseLength.SHORT, PhraseLength.MEDIUM, PhraseLength.LONG)
    used = {length: 0 for length in order}
    result = []
    for index in range(target_count):
        length = order[index % len(order)]
        choices = catalog[length]
        text = choices[used[length] % len(choices)]
        used[length] += 1
        result.append(EnrollmentPhrase(text=text, language=locale, length_class=length))
    return tuple(result)


class EnrollmentSessionStore:
    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self._lock = RLock()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS enrollment_sessions (
                    session_id TEXT PRIMARY KEY,
                    profile_user_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    target_count INTEGER NOT NULL,
                    accepted_sample_ids_json TEXT NOT NULL,
                    phrases_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    termination_reason TEXT,
                    last_reason_code TEXT
                )
            """)
            connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_enrollment_active_source
                ON enrollment_sessions(source_id)
                WHERE status = 'ACTIVE'
            """)

    def create(self, session: EnrollmentSession) -> EnrollmentSession:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO enrollment_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._values(session),
            )
        return session

    def get(self, session_id: str) -> EnrollmentSession:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM enrollment_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise EnrollmentNotFound(session_id)
        return self._from_row(row)

    def get_active_for_source(self, source_id: str) -> EnrollmentSession | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM enrollment_sessions WHERE source_id = ? AND status = 'ACTIVE'",
                (source_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def mutate(self, session_id: str, operation) -> EnrollmentSession:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM enrollment_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise EnrollmentNotFound(session_id)
            updated = operation(self._from_row(row))
            connection.execute(
                """UPDATE enrollment_sessions SET
                    profile_user_id=?, source_id=?, language=?, target_count=?,
                    accepted_sample_ids_json=?, phrases_json=?, status=?,
                    termination_reason=?, last_reason_code=? WHERE session_id=?""",
                self._values(updated)[1:] + (session_id,),
            )
            connection.commit()
            return updated

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _values(session: EnrollmentSession) -> tuple:
        phrases = [
            {"text": phrase.text, "language": phrase.language, "length_class": phrase.length_class.value}
            for phrase in session.phrases
        ]
        return (
            session.session_id, session.profile_user_id, session.source_id, session.language,
            session.target_count, json.dumps(session.accepted_sample_ids), json.dumps(phrases),
            session.status.value, session.termination_reason, session.last_reason_code,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> EnrollmentSession:
        phrases = tuple(
            EnrollmentPhrase(
                text=item["text"], language=item["language"],
                length_class=PhraseLength(item["length_class"]),
            )
            for item in json.loads(row["phrases_json"])
        )
        return EnrollmentSession(
            session_id=row["session_id"], profile_user_id=row["profile_user_id"],
            source_id=row["source_id"], language=row["language"], target_count=row["target_count"],
            accepted_sample_ids=tuple(json.loads(row["accepted_sample_ids_json"])),
            phrases=phrases, status=EnrollmentStatus(row["status"]),
            termination_reason=row["termination_reason"], last_reason_code=row["last_reason_code"],
        )


class EnrollmentService:
    def __init__(self, store: EnrollmentSessionStore, phrase_generator: PhraseGenerator | None = None):
        self.store = store
        self.phrase_generator = phrase_generator

    def start(self, profile_user_id: str, source_id: str, language: str, target_count: int = 6) -> EnrollmentSession:
        profile_user_id = _required(profile_user_id, "profile_user_id")
        source_id = _required(source_id, "source_id")
        language = _required(language, "language")
        if type(target_count) is not int or not 1 <= target_count <= 24:
            raise ValueError("target_count must be between 1 and 24")
        active = self.store.get_active_for_source(source_id)
        if active is not None:
            if active.profile_user_id == profile_user_id:
                return active
            raise EnrollmentConflict("ACTIVE_ENROLLMENT_CONFLICT")
        phrases = self._phrases(language, target_count)
        return self.store.create(EnrollmentSession(
            session_id=f"enr_{uuid.uuid4().hex}", profile_user_id=profile_user_id,
            source_id=source_id, language=language, target_count=target_count,
            accepted_sample_ids=(), phrases=phrases, status=EnrollmentStatus.ACTIVE,
        ))

    def get(self, session_id: str) -> EnrollmentSession:
        return self.store.get(session_id)

    def record_attempt(self, session_id: str, status: str, *, sample_id: str | None = None,
                       reason_code: str | None = None) -> EnrollmentSession:
        if status not in {"ACCEPTED", "REJECTED", "FAILED"}:
            raise ValueError("invalid attempt status")
        if status == "ACCEPTED" and not sample_id:
            raise ValueError("accepted attempt requires sample_id")

        def update(session: EnrollmentSession) -> EnrollmentSession:
            if session.status is not EnrollmentStatus.ACTIVE:
                raise EnrollmentConflict("enrollment session is terminal")
            samples = session.accepted_sample_ids
            if status == "ACCEPTED":
                if sample_id in samples:
                    raise EnrollmentConflict("sample already recorded")
                samples += (sample_id,)
            completed = len(samples) == session.target_count
            return EnrollmentSession(
                **{
                    **asdict(session),
                    "accepted_sample_ids": samples,
                    "phrases": session.phrases,
                    "status": EnrollmentStatus.COMPLETED if completed else EnrollmentStatus.ACTIVE,
                    "last_reason_code": None if status == "ACCEPTED" else reason_code,
                }
            )

        return self.store.mutate(session_id, update)

    def terminate(self, session_id: str, reason: str) -> EnrollmentSession:
        reason = _required(reason, "reason")

        def update(session: EnrollmentSession) -> EnrollmentSession:
            if session.status is EnrollmentStatus.COMPLETED:
                return session
            if session.status is EnrollmentStatus.TERMINATED:
                if session.termination_reason == reason:
                    return session
                raise EnrollmentConflict("enrollment session already terminated")
            return EnrollmentSession(
                **{
                    **asdict(session), "accepted_sample_ids": session.accepted_sample_ids,
                    "phrases": session.phrases, "status": EnrollmentStatus.TERMINATED,
                    "termination_reason": reason,
                }
            )

        return self.store.mutate(session_id, update)

    def _phrases(self, language: str, target_count: int) -> tuple[EnrollmentPhrase, ...]:
        if self.phrase_generator is not None:
            try:
                generated = tuple(self.phrase_generator.generate(language, target_count))
                if self._valid_plan(generated, language, target_count):
                    return generated
            except Exception:
                pass
        return deterministic_phrase_plan(language, target_count)

    @staticmethod
    def _valid_plan(phrases, language, target_count) -> bool:
        return (
            len(phrases) == target_count
            and all(isinstance(item, EnrollmentPhrase) and item.text.strip() and item.language == language for item in phrases)
        )


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError(f"invalid {name}")
    return value.strip()
