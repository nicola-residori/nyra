"""Bounded read-only discovery across language and naming differences."""
import re
import unicodedata

_TOPIC_GROUPS = (
    {"solar", "solare", "fotovoltaico", "fotovoltaica", "photovoltaic", "pv"},
    {"battery", "batteria", "batterie", "accumulo"},
    {"energy", "energia"},
    {"power", "potenza"},
    {"production", "produzione", "generated", "generata"},
)
_FILLERS = {"sensor", "sensors", "sensore", "sensori", "device", "dispositivo", "dispositivi", "impianto", "report", "resoconto", "stato", "status", "del", "della", "di", "the", "of", "my"}
_MEASUREMENT_ATTRIBUTES = ("unit_of_measurement", "device_class", "state_class")


def _tokens(value):
    normalized = unicodedata.normalize("NFKD", value.casefold())
    tokens = set(re.findall(r"[^\W_]+", "".join(c for c in normalized if not unicodedata.combining(c))))
    aliases = set().union(*_TOPIC_GROUPS)
    for token in tuple(tokens):
        numbered = re.fullmatch(r"([^\W\d_]+)\d+", token)
        if numbered and numbered[1] in aliases:
            tokens.add(numbered[1])
    return tokens


def discover_resources(states, query, allowed_ids=None, limit=20, *, focus=""):
    focus_tokens = _tokens(focus) if isinstance(focus, str) else set()
    # User-named domains constrain model-added generic measurement hints.
    focus_domains = [group for group in _TOPIC_GROUPS[:2] if focus_tokens.intersection(group)]
    query_tokens = _tokens(query) - _FILLERS
    groups = {frozenset(next((group for group in _TOPIC_GROUPS if token in group), {token})) for token in query_tokens}
    matches = []
    for native in states:
        entity = native.get("entity_id")
        if not isinstance(entity, str) or (allowed_ids is not None and entity not in allowed_ids):
            continue
        attrs = native.get("attributes") or {}
        name = attrs.get("friendly_name")
        tokens = _tokens(f"{entity} {name or ''}")
        if focus_domains and not any(tokens.intersection(group) for group in focus_domains):
            continue
        matched_groups = sum(bool(tokens.intersection(group)) for group in groups)
        if groups and not matched_groups:
            continue
        item = {"entity_id": entity, "name": name, "state": native.get("state")}
        metadata = {key: attrs[key] for key in _MEASUREMENT_ATTRIBUTES if key in attrs}
        if metadata:
            item["attributes"] = metadata
        for key in ("last_updated", "last_changed"):
            if isinstance(native.get(key), str):
                item[key] = native[key]
        # Surface available measurements before setpoints and forecast/helper entities.
        rank = (
            native.get("state") in {"unavailable", "unknown"},
            not (entity.startswith("sensor.") and attrs.get("device_class") in {"power", "energy"}),
            bool(tokens.intersection({"forecast", "estimated", "stimata", "stimato", "previsione"})),
            -matched_groups,
        )
        matches.append((rank, item))
    matches.sort(key=lambda pair: pair[0])
    return {"items": [item for _, item in matches[:limit]], "truncated": len(matches) > limit}
