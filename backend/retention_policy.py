"""Conservative English personal-fact eligibility, independent of model labels.

This is a grammar-based gate, not semantic understanding. An unknown or ambiguous
construction stays in conversation history instead of becoming a personal fact.
"""

import re
from dataclasses import dataclass

POLICY_VERSION = 1

_WRAPPER = re.compile(
    r"^(?:(?:did|have)\s+i\s+(?:ever\s+)?(?:mention(?:ed)?|tell|told)"
    r"(?:\s+(?:you|to\s+you))?(?:\s+that)?"
    r"|(?:do|can|could|would|will)\s+you\s+(?:please\s+)?"
    r"(?:remember|recall|note|keep\s+in\s+mind)(?:\s+that)?"
    r"|(?:do|did)\s+you\s+know(?:\s+that)?)\s*[:,]?\s+", re.I,
)
_SOCIAL = re.compile(r"^(?:by the way|you know|for the record|actually|correction|update)\s*[:,]?\s+", re.I)
_QUESTION_OR_UNCERTAIN = re.compile(
    r"^(?:who|what|where|when|why|how|which|is|are|am|was|were|do|does|did|"
    r"has|have|had|can|could|should|would|will|if|whether|suppose|imagine|"
    r"maybe|perhaps|hypothetically)\b", re.I,
)
_I_CLAIM = re.compile(
    r"\bi(?:['’]m|['’]ve|['’]d|['’]ll|\s+(?:(?:do\s+not|don't|dont|never|"
    r"did\s+not|didn't|no\s+longer)\s+)?(?:am|was|have|had|prefer|like|love|"
    r"enjoy|dislike|hate|live|lived|grew|moved|work|worked|study|studied|own|"
    r"owned|lost|found|met|visited|won|survived|fought|rescued|bought|sold|"
    r"learned|learnt|trained|married|celebrated|helped|promised|proposed|"
    r"remember|saved|travelled|traveled|went|returned|arrived|saw|witnessed|escaped))\s+\S", re.I,
)
_MY_CLAIM = re.compile(
    r"\b(?:my|our)\s+[^.!?\n]{1,100}?(?:\s+(?:is|are|was|were|has|have|"
    r"lives?|works?|moved|died|married|visited|won|likes?|prefers?)\s+|:\s*)\S", re.I,
)
_RELATION = re.compile(r"\b(?:sister|brother|mother|father|parent|partner|wife|husband|daughter|son|friend|family|cousin)\b", re.I)
_NAMED_RELATION = re.compile(
    r"\bmy\s+(?:sister|brother|mother|father|partner|wife|husband|daughter|son|friend|cousin)"
    r"\s+(?:named\s+)?[A-Z][a-z]+\b"
)
_REVERSE_MY = re.compile(r"\b[^.!?\n]{1,80}?\s+(?:is|are|was|were)\s+my\s+\S", re.I)
_OBJECT_EVENT = re.compile(
    r"\b[^.!?\n]{1,80}?\s+(?:saved|rescued|helped|attacked|robbed|taught|healed|"
    r"hired|invited|gave|betrayed|injured|cured)\s+(?:me\b|my\s+\S)", re.I,
)
_INFORMATION_SEEKING = re.compile(
    r"^(?:my\s+(?:question|request|inquiry|query)\b|"
    r"i['’]d\s+like\s+to\s+know\b|"
    r"i(?:['’]m|\s+(?:am|was|have\s+been|had\s+been))?\s+(?:wondering|curious|not\s+sure|uncertain|wonder|ask|asked|asking|"
    r"(?:want|need)\s+to\s+(?:know|ask)|would\s+like\s+to\s+know|"
    r"have\s+(?:(?:a|some)\s+questions?|no\s+idea))\b)", re.I,
)
_RETRACTION = re.compile(r"\b(?:just kidding|only joking|that was a joke)\b", re.I)
_QUALIFIED = re.compile(r"\b(?:pretend that|not sure whether|not sure if|not true that|false that|deny that|never said)\b", re.I)
_HYPOTHETICAL = re.compile(r"^(?:if|what\s+if|suppose|imagine|maybe|perhaps|hypothetically)\b", re.I)
_CONFIRMATION = re.compile(r"^(?:is|are|am|was|were|do|does|did|has|have|had|can\s+i|could\s+i|would\s+i|should\s+i)\b", re.I)
_ASSERTIVE_CLAUSE = re.compile(r"\b(?:because|since|given\s+that|now\s+that|after)\s+((?:i|my|our)\b.+)", re.I)
_HOME = re.compile(r"\bmy\s+(?:home|house|hometown)\s+(?:in|near|at)\s+[^.!?\n]+", re.I)
_TAG = re.compile(r",?\s+(?:right|remember|okay|ok|you know)\s*\?$", re.I)


@dataclass(frozen=True)
class PersonalEvidence:
    statements: tuple[str, ...]
    category: str
    reason: str

    @property
    def eligible(self):
        return bool(self.statements)


def _sentences(text):
    """Small sentence splitter that preserves common name abbreviations."""
    start = 0
    for boundary in re.finditer(r"[.!?](?=\s|$)|\n", text):
        end = boundary.end()
        if boundary.group() == "." and re.search(r"\b(?:Dr|Mr|Mrs|Ms|Prof|St|Jr|Sr)\.$", text[start:end], re.I):
            continue
        sentence = text[start:end].strip()
        if sentence:
            yield sentence
        start = end
    if text[start:].strip():
        yield text[start:].strip()


def _category(statement):
    if re.match(r"^(?:correction|actually|update)\b", statement, re.I):
        return "correction"
    if _RELATION.search(statement):
        return "relationship"
    if re.search(r"\b(?:prefer|preference|favorite|favourite|like|love|enjoy|dislike|hate)\b", statement, re.I):
        return "preference"
    if (re.search(r"\b(?:live|lived|home|hometown|grew up|moved)\b", statement, re.I)
            or re.search(r"\bi(?:\s+am|['’]m)\s+from\b", statement, re.I)):
        return "location"
    if re.search(r"\b(?:name|called|work|study|studied|occupation)\b", statement, re.I):
        return "identity"
    if re.search(r"\b(?:lost|found|met|visited|won|survived|fought|rescued|bought|sold|learned|trained|married|celebrated|promised|proposed|traveled|travelled|went|returned|arrived|saw|witnessed|escaped|saved|helped|attacked|robbed|taught|healed|hired|invited|gave|betrayed|injured|cured)\b", statement, re.I):
        return "event"
    return "other"


def personal_evidence(text: str) -> PersonalEvidence:
    evidence = []
    categories = []
    if _RETRACTION.search(text):
        return PersonalEvidence((), "ignore", "Ambiguous, hypothetical, or explicitly qualified statement")
    for original in _sentences(text):
        if _QUALIFIED.search(original):
            continue
        candidate = original
        social = _SOCIAL.match(candidate)
        if social:
            candidate = candidate[social.end():]
        wrapper = _WRAPPER.match(candidate)
        if wrapper:
            candidate = candidate[wrapper.end():]
        elif candidate.rstrip().endswith("?"):
            if _HYPOTHETICAL.match(candidate):
                continue
            tag = _TAG.search(candidate)
            clause = _ASSERTIVE_CLAUSE.search(candidate)
            if tag:
                candidate = candidate[:tag.start()]
            elif clause:
                candidate = clause.group(1)
            elif not _CONFIRMATION.match(candidate):
                # A request can explicitly identify a relative/home without
                # asserting the answer to the question itself.
                nominal = _NAMED_RELATION.search(candidate) or _HOME.search(candidate)
                if nominal:
                    statement = nominal.group().rstrip("?").rstrip()
                    evidence.append(statement)
                    categories.append(_category(statement))
                continue
            else:
                # A yes/no confirmation is not evidence of its proposed answer.
                continue
        if _QUESTION_OR_UNCERTAIN.match(candidate):
            continue
        if _INFORMATION_SEEKING.match(candidate):
            continue
        match = (_I_CLAIM.search(candidate) or _MY_CLAIM.search(candidate)
                 or _NAMED_RELATION.search(candidate) or _REVERSE_MY.search(candidate)
                 or _OBJECT_EVENT.search(candidate))
        if match:
            # Verbatim source clause; remove only the conversational wrapper,
            # never negate, rewrite, or fill in a missing factual value.
            statement = candidate[match.start():].strip()
            if original.rstrip().endswith("?"):
                statement = statement.rstrip("?").rstrip()
            evidence.append(statement)
            categories.append(_category(original))
    if not evidence:
        return PersonalEvidence((), "ignore", "No explicit personal assertion; general questions and requests are not player facts")
    category = next((c for c in categories if c != "other"), "other")
    return PersonalEvidence(tuple(evidence), category, "Explicit source-grounded personal assertion")


def retention_decision(source, model_category):
    assessment = personal_evidence(source["content"])
    return {
        "source_message_id": source["message_id"], "model_category": model_category,
        "effective_category": assessment.category, "retained": assessment.eligible,
        "reason": assessment.reason, "policy_version": POLICY_VERSION,
    }
