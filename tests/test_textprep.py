from __future__ import annotations

import pytest

from helpers import synthetic_doc
from mindmap.config import EXCERPT_MAX_CHARS, MAX_INPUT_BYTES
from mindmap.errors import InputError
from mindmap.textprep import load_document, segment, select_passages

def test_short_document_passes_through_verbatim() -> None:
    doc = "Plants make sugar. They need light."
    excerpt = select_passages(doc)
    assert excerpt.text == doc
    assert excerpt.stats.passthrough and excerpt.stats.sent_ratio == 1.0


@pytest.mark.parametrize("size", [1_000, 100_000, 1_000_000])
def test_excerpt_is_bounded_for_any_length(size: int) -> None:
    excerpt = select_passages(synthetic_doc(size))
    assert len(excerpt.text) <= EXCERPT_MAX_CHARS
    assert excerpt.stats.sent_chars == len(excerpt.text)


def test_selection_is_deterministic() -> None:
    doc = synthetic_doc(80_000)
    assert select_passages(doc).text == select_passages(doc).text


def test_novelty_prefers_material_not_in_map() -> None:
    covered = "Photosynthesis uses chlorophyll to capture light energy in the leaf. " * 1
    novel = "Quantum tunnelling explains electron transfer in the reaction centre."
    filler = " ".join(f"Covered sentence {i} about photosynthesis chlorophyll light leaf energy." for i in range(400))
    doc = f"{covered} {filler} {novel}"
    excerpt = select_passages(doc, budget_chars=300, novelty_against=["Photosynthesis", "chlorophyll light leaf energy"])
    assert "Quantum tunnelling" in excerpt.text


def test_run_on_text_without_punctuation_is_split() -> None:
    doc = "word " * 50_000
    assert max(len(s) for s in segment(doc)) <= 600
    assert len(select_passages(doc).text) <= EXCERPT_MAX_CHARS


@pytest.mark.parametrize(
    "raw, message",
    [
        (b"", "empty"),
        (b"   \n\t  ", "empty"),
        (b"\xff\xfe\x00bad", "not valid UTF-8"),
        (b"a" * (MAX_INPUT_BYTES + 1), "limit"),
    ],
)
def test_load_document_rejects(raw: bytes, message: str) -> None:
    with pytest.raises(InputError, match=message):
        load_document(raw)


def test_load_document_strips_control_characters() -> None:
    assert load_document(b"Hello\x00 world\x1b\r\nnext") == "Hello world\nnext"
