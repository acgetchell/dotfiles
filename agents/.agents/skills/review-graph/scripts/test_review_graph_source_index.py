"""Source locations stay bounded, literal, and separate from inspection proof."""

import pytest
from review_graph_source_index import navigation_bytes, source_excerpt


def test_navigation_skips_documentation_comments_and_raw_strings() -> None:
    content = (
        "/*\nfn documentation() {}\n/* nested */\n*/\n"
        'const EXAMPLE: &str = r##"\nfn example() {}\n"##;\n'
        "// fn comment() {}\n"
        "pub async fn actual(\n    value: usize,\n) -> usize { value }\n" + "// filler\n" * 1000
    ).encode()
    excerpt, used = source_excerpt("source.rs", content, 1024)
    locations = excerpt["navigation"]["locations"]
    assert len(locations) == 1
    assert locations[0]["text"] == "pub async fn actual(\n    value: usize,\n) -> usize {"
    assert (locations[0]["start_line"], locations[0]["end_line"]) == (9, 11)
    assert locations[0]["window_complete"] is True
    assert not excerpt["complete"]
    assert not excerpt["navigation"]["complete"]
    assert used == navigation_bytes(excerpt["navigation"]) + len(excerpt["text"].encode()) <= 1024


@pytest.mark.parametrize(
    ("signature", "expected_text", "complete"),
    [
        (
            "pub fn short(\n    a: u8,\n    b: u8,\n    c: u8,\n    d: u8,\n) -> u8 {",
            "pub fn short(\n    a: u8,\n    b: u8,\n    c: u8,\n    d: u8,\n) -> u8 {",
            True,
        ),
        (
            "pub fn long(\n    a: u8,\n    b: u8,\n    c: u8,\n    d: u8,\n    e: u8,\n    f: u8,\n) -> u8 {",
            "pub fn long(\n    a: u8,\n    b: u8,\n    c: u8,\n    d: u8,\n    e: u8,",
            False,
        ),
    ],
    ids=["boundary-on-sixth-line", "boundary-after-line-limit"],
)
def test_signature_completeness_accounts_for_line_limit(signature: str, expected_text: str, complete: bool) -> None:
    assert len(signature.encode()) < 192
    content = (signature + " a }\n" + "// filler\n" * 200).encode()

    excerpt, used = source_excerpt("lib.rs", content, 1024)

    assert excerpt["navigation"]["locations"] == [{"kind": "fn", "start_line": 1, "end_line": 6, "text": expected_text, "window_complete": complete}]
    assert used <= 1024


def test_signature_completeness_accounts_for_byte_limit() -> None:
    signature = "pub fn long(" + "value_" * 40 + ": u8) {"
    content = (signature + "}\n" + "// filler\n" * 200).encode()

    excerpt, _ = source_excerpt("lib.rs", content, 1024)

    location = excerpt["navigation"]["locations"][0]
    assert location["window_complete"] is False
    assert location["text"] == signature[:192]
    assert (location["start_line"], location["end_line"]) == (1, 1)


@pytest.mark.parametrize("budget", [0, 1, 19, 256, 512, 16384])
def test_utf8_and_small_budgets_never_exceed_the_allocation(budget: int) -> None:
    content = ("//! λ documentation\n" * 100 + "pub fn créer() {}\n").encode()
    excerpt, used = source_excerpt("source.rs", content, budget)
    assert used <= budget
    assert excerpt["complete"] == (excerpt["text"].encode() == content)
    assert used == len(excerpt["text"].encode()) + (navigation_bytes(excerpt["navigation"]) if "navigation" in excerpt else 0)


def test_complete_source_does_not_need_a_duplicate_index() -> None:
    content = b"pub fn new() {}\n"
    excerpt, used = source_excerpt("lib.rs", content, 500)
    assert excerpt == {"text": content.decode(), "complete": True}
    assert used == len(content)
