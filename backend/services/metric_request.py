"""Explicit aggregate identity; a sum or stock level cannot answer an average."""
import re
from services.semantic_graph import normalize_text


def average_subject(prompt: str) -> str | None:
    text = normalize_text(prompt)
    match = re.search(r"^(?:(?:cual es|cuanto es|calculame|calcula|mostrame|quiero saber|dame)\s+)?(?:(?:el|la|un|una)\s+)?(?:promedio|media|average)\s+(?:de\s+|del\s+|la\s+|el\s+|of\s+)+(.+)", text)
    if not match:
        return None
    subject = re.split(r"\b(?:para|durante|segun|entre|por|de ese|de esa)\b", match[1])[0].strip()
    return subject or None


def subject_matches(subject: str, item: dict) -> bool:
    def words(text):
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ").replace(".", " ")
        return {word.rstrip("s") for word in normalize_text(text).split()
                if word not in {"de", "del", "la", "el", "los", "las"}}
    identities = [str(item.get(key) or "") for key in ["name", "key", "semantic_key", "business_name"]]
    identities.extend(str(alias) for alias in item.get("aliases") or [])
    requested = words(subject)
    return bool(requested) and any(requested.issubset(words(identity)) for identity in identities)


def known_average_subject(prompt: str, graph: dict) -> bool:
    subject = average_subject(prompt)
    return bool(subject) and any(subject_matches(subject, item) for item in
                                 [*graph.get("metrics", []), *graph.get("dimensions", [])])


def matches_requested_average(prompt: str, metric: dict) -> bool:
    subject = average_subject(prompt)
    if not subject:
        return True
    identity = normalize_text(" ".join([str(metric.get("name") or ""),
                                       str(metric.get("key") or "").replace("_", " "),
                                       *[str(alias) for alias in metric.get("aliases") or []]]))
    if not re.search(r"\b(?:promedio|media|average|avg|mean)\b", identity):
        return False
    return subject_matches(subject, metric)
