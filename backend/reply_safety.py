"""Narrow, deterministic guards over actual user evidence, not generated facts."""

import re

from memory_store import _keywords
from retention_policy import personal_evidence

_CLAIM = re.compile(r"^(my\s+[^.!?\n]{1,100}?)\s+(?:is|are)\s+([^.!?\n]+)[.!]?$", re.I)
_CORRECTION = re.compile(r"^(?:correction|actually|update)(?:\s*[:,]\s*|\s+)", re.I)
_FIRST_PERSON = re.compile(r"\b(?:i|my|me|we|our|us)\b", re.I)
_OVERVIEW = re.compile(
    r"\b(?:what|which|tell)\b.*\b(?:remember|recall|know|learned|learnt|memories)\b.*\babout me\b", re.I
)


def _personal_overview(statements):
    facts = []
    seen = set()
    used = 0
    for text in statements:
        for fact in personal_evidence(text).statements:
            key = _normalize(fact)
            if key in seen or len(fact) > 600 or used + len(fact) > 1200:
                continue
            facts.append(fact)
            seen.add(key)
            used += len(fact)
            if len(facts) == 5:
                break
        if len(facts) == 5:
            break
    if not facts:
        return "I don't have that information in the available context."
    return "Here are some things you've told me: " + "; ".join(f'“{fact}”' for fact in facts)


def _normalize(text):
    return " ".join(text.strip().strip('"“”').rstrip(".!").casefold().split())


def evidence_statements(history, memories, summary):
    """Only user evidence; assistant turns can never trigger these guards."""
    # Summary and keyword entries predate the recent history. This ordering is
    # useful for recognizing an explicit correction after older claims.
    older = [(max(e["source_message_ids"]), e["statement"]) for e in summary["entries"]] if summary else []
    older.extend((m["message_id"], m["content"]) for m in memories)
    statements = [text for _source_id, text in sorted(set(older))]
    statements.extend(m["content"] for m in history if m["role"] == "user")
    return statements


def safe_memory_reply(reply: str, question: str, statements: list[str]) -> str:
    """Preserve source wording instead of guessing pronouns or conflict reasons.

    Conflict recognition deliberately covers only complete, simple 'My ... is/
    are ...' statements. It is not semantic conflict detection. Longer or more
    complex statements remain the model's responsibility.
    """
    if _OVERVIEW.search(question):
        return _personal_overview(statements)
    query_words = _keywords(question)
    topics = {}
    for text in [*statements, question]:
        if len(text) > 600:
            continue
        cleaned = text.strip()
        correction = _CORRECTION.match(cleaned)
        if correction:
            cleaned = cleaned[correction.end():]
        match = _CLAIM.fullmatch(cleaned)
        if not match:
            continue
        topic, value = match.groups()
        if not _normalize(value):
            continue
        topic_words = _keywords(topic)
        if not topic_words or not topic_words.issubset(query_words):
            continue
        key = _normalize(topic)
        if correction:
            topics[key] = {}
        topics.setdefault(key, {})[_normalize(value)] = text.strip()
    for alternatives in topics.values():
        if len(alternatives) > 1:
            first, second = list(alternatives.values())[:2]
            return (
                f'You previously said: “{first}” and “{second}” '
                "I'm not sure which is current; could you clarify?"
            )
    if _FIRST_PERSON.search(reply):
        for statement in [*statements, question]:
            if len(statement) <= 600 and _normalize(reply) == _normalize(statement):
                return f'You previously said: “{statement.strip()}”'
    return reply
