"""Deterministic document handling. No model is used anywhere in this module.

`select_passages` is plain extractive selection (TF-IDF-style salience, optional
lexical novelty against an existing map). It is named for what it does; it does
not "summarise". Its job is to make the model's input a fixed size, whatever the
document length.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel

from mindmap.config import EXCERPT_MAX_CHARS, MAX_INPUT_BYTES, NOVELTY_WEIGHT, SEGMENT_MAX_CHARS
from mindmap.errors import InputError

_CONTROL_EXCEPT_WS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_TOKEN = re.compile(r"[a-z0-9]+")
GAP_MARKER = " [...] "

STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further had
    has have having he her here hers him his how i if in into is it its itself just me more most my
    no nor not now of off on once only or other our ours out over own same she should so some such
    than that the their them then there these they this those through to too under until up very
    was we were what when where which while who whom why will with would you your yours also may
    might must shall one two new use used using""".split()
)


def load_document(raw: bytes) -> str:
    """Validate and clean an untrusted document. Raises InputError before any model call."""
    if len(raw) > MAX_INPUT_BYTES:
        raise InputError(f"document is {len(raw):,} bytes; the limit is {MAX_INPUT_BYTES:,}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(f"document is not valid UTF-8 text (byte {exc.start})") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_EXCEPT_WS.sub("", text)
    if not text.strip():
        raise InputError("document is empty")
    return text


def content_tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def segment(text: str) -> list[str]:
    """Split into sentence-like segments, each at most SEGMENT_MAX_CHARS (hard-split at spaces)."""
    segments: list[str] = []
    for paragraph in _PARAGRAPH_SPLIT.split(text):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        for sentence in _SENTENCE_SPLIT.split(paragraph):
            sentence = sentence.strip()
            while len(sentence) > SEGMENT_MAX_CHARS:
                cut = sentence.rfind(" ", 0, SEGMENT_MAX_CHARS)
                cut = cut if cut > 0 else SEGMENT_MAX_CHARS
                segments.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                segments.append(sentence)
    return segments


class ExcerptStats(BaseModel):
    doc_chars: int
    sent_chars: int
    segments_total: int
    segments_sent: int
    passthrough: bool

    @property
    def sent_ratio(self) -> float:
        return self.sent_chars / self.doc_chars if self.doc_chars else 1.0


@dataclass(frozen=True)
class Excerpt:
    text: str
    stats: ExcerptStats


def select_passages(
    text: str,
    budget_chars: int = EXCERPT_MAX_CHARS,
    novelty_against: Iterable[str] | None = None,
) -> Excerpt:
    """Pick the most salient (and, for grow, most novel) segments that fit in `budget_chars`.

    Deterministic: same input -> same output. Selected segments keep document order,
    with GAP_MARKER where text was skipped. A document that already fits passes through.
    """
    stripped = text.strip()
    if len(stripped) <= budget_chars:
        n = len(segment(stripped))
        stats = ExcerptStats(doc_chars=len(stripped), sent_chars=len(stripped), segments_total=n,
                             segments_sent=n, passthrough=True)
        return Excerpt(stripped, stats)

    segments = segment(stripped)
    token_sets = [set(content_tokens(s)) for s in segments]
    doc_freq: Counter[str] = Counter()
    for tokens in token_sets:
        doc_freq.update(tokens)
    n_segments = len(segments)
    map_tokens = set(content_tokens(" ".join(novelty_against))) if novelty_against else set()

    scored: list[tuple[float, int]] = []
    seen_text: set[str] = set()
    for idx, (seg, tokens) in enumerate(zip(segments, token_sets)):
        key = seg.lower()
        if not tokens or key in seen_text:  # skip empty and exact-duplicate segments
            continue
        seen_text.add(key)
        # Sum of IDF over distinct terms, normalised by sqrt(#terms): rewards many rare terms
        # without letting long segments win on length alone. (guessed weighting)
        idf_sum = sum(math.log(n_segments / doc_freq[t]) + 1.0 for t in tokens)
        score = idf_sum / math.sqrt(len(tokens))
        if map_tokens:
            overlap = len(tokens & map_tokens) / len(tokens)
            score *= 1.0 - NOVELTY_WEIGHT * overlap
        scored.append((score, idx))

    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen: list[int] = []
    used = 0
    for _score, idx in scored:
        cost = len(segments[idx]) + len(GAP_MARKER)  # worst case: every segment separated by a gap
        if used + cost > budget_chars:
            continue
        chosen.append(idx)
        used += cost

    chosen.sort()
    parts: list[str] = []
    previous = -2
    for idx in chosen:
        if parts:
            parts.append(" " if idx == previous + 1 else GAP_MARKER)
        parts.append(segments[idx])
        previous = idx
    excerpt = "".join(parts)
    stats = ExcerptStats(doc_chars=len(stripped), sent_chars=len(excerpt), segments_total=n_segments,
                         segments_sent=len(chosen), passthrough=False)
    return Excerpt(excerpt, stats)
