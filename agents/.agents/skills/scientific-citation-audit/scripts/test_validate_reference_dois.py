#!/usr/bin/env python3
"""Fixture tests for validate_reference_dois.py."""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).with_name("validate_reference_dois.py")
SPEC = importlib.util.spec_from_file_location("validate_reference_dois", SCRIPT)
if SPEC is None or SPEC.loader is None:
    message = "validate_reference_dois.py could not be loaded"
    raise RuntimeError(message)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def metadata(title: str, *, family: str = "Shewchuk", year: int = 1997) -> dict[str, object]:
    """Return a minimal CSL-shaped metadata fixture."""
    return {"title": title, "author": [{"family": family, "given": "J. R."}], "issued": {"date-parts": [[year]]}, "container-title": "Fixture Journal"}


def test_extracts_doi_label_with_parentheses_and_angle_tokens() -> None:
    """DOI labels preserve full DOI text even when URLs are Markdown-hostile."""
    markdown = (
        "- Field. DOI: [10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H]"
        "(https://doi.org/10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H)"
    )

    entries = MODULE.extract_entries(markdown)

    assert len(entries) == 1
    assert entries[0].doi.value == "10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H"


def test_extracts_markdown_link_destination_with_balanced_parentheses() -> None:
    """Markdown DOI links with balanced parentheses are parsed as one destination."""
    markdown = "- Field. [doi](https://doi.org/10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H)"

    entries = MODULE.extract_entries(markdown)

    assert len(entries) == 1
    assert entries[0].doi.value == "10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H"


def test_extracts_raw_url_with_trailing_period() -> None:
    """Raw DOI URLs tolerate prose trailing punctuation."""
    markdown = "- Shewchuk. https://doi.org/10.1007/PL00009321."

    entries = MODULE.extract_entries(markdown)

    assert len(entries) == 1
    assert entries[0].doi.value == "10.1007/PL00009321"


def test_validation_flags_author_mismatch() -> None:
    """A matching title with unrelated local author text is still a mismatch."""
    entry = MODULE.DoiEntry(
        doi=MODULE.Doi.parse("10.1007/PL00009321"),
        line=1,
        entry="- Wrong, A. Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates. 1997.",
    )

    result = MODULE.validate_entry(
        entry,
        1.0,
        0.45,
        fetcher=lambda _doi, _timeout: metadata(
            "Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates", family="Shewchuk", year=1997
        ),
    )

    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.author_score == 0.0
    assert "authors" in result.message


def test_validation_accepts_matching_title_author_and_year() -> None:
    """Matching title, author, and year produce an OK result."""
    entry = MODULE.DoiEntry(
        doi=MODULE.Doi.parse("10.1007/PL00009321"),
        line=1,
        entry="- Shewchuk, J. R. Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates. 1997.",
    )

    result = MODULE.validate_entry(
        entry,
        1.0,
        0.45,
        fetcher=lambda _doi, _timeout: metadata(
            "Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates", family="Shewchuk", year=1997
        ),
    )

    assert result.status == MODULE.AuditStatus.OK


def test_validation_reports_malformed_fetcher_response() -> None:
    """Malformed resolver data should produce a failed audit result."""
    entry = MODULE.DoiEntry(doi=MODULE.Doi.parse("10.1007/PL00009321"), line=1, entry="- Fixture entry.")

    def malformed_fetcher(_doi: object, _timeout: float) -> dict[str, object]:
        message = "DOI resolver response must be a JSON object"
        raise TypeError(message)

    result = MODULE.validate_entry(entry, 1.0, 0.45, fetcher=malformed_fetcher)

    assert result.status == MODULE.AuditStatus.FAIL
    assert result.message == "TypeError: DOI resolver response must be a JSON object"


@pytest.mark.parametrize("heading", ["# Project\n\n", "# Project\n", "### Project\n", "   ###### Project\n", "#\tProject\n", "#\n"])
def test_resolved_badge_needs_context_instead_of_reporting_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], heading: str
) -> None:
    path = tmp_path / "README.md"
    path.write_text(f"{heading}[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.123.svg)](https://doi.org/10.5281/zenodo.123)\n", encoding="utf-8")
    original = MODULE.validate_entries
    monkeypatch.setattr(
        MODULE,
        "validate_entries",
        lambda entries, timeout, score: original(entries, timeout, score, lambda *_: metadata("Project", family="Author", year=2026)),
    )
    assert MODULE.run([str(path), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)[0]
    assert result["status"] == "INSUFFICIENT_CONTEXT"
    assert result["line"] == heading.count("\n") + 1
    assert result["resolved_title"] == "Project"
    assert result["resolved_authors"] == ["Author"]
    assert result["title_score"] is None
    assert result["author_score"] is None
    assert "no bibliographic context" in result["message"]


def test_heading_after_badge_terminates_entry() -> None:
    badge = "[![DOI](https://example.org/badge.svg)](https://doi.org/10.1234/test)"
    entry = MODULE.extract_entries(f"{badge}\n## Unrelated section\nOther text.")[0]
    assert entry.entry == badge
    assert entry.badge_only


def test_badge_does_not_hide_contradictory_bibliographic_context() -> None:
    entry = MODULE.extract_entries("Wrong. Unrelated science. 2001.\n[![DOI](https://example.org/badge.svg)](https://doi.org/10.1234/test)")[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Actual title", year=2026))
    assert result.status == MODULE.AuditStatus.MISMATCH


def test_unresolved_badge_is_still_a_resolution_failure() -> None:
    entry = MODULE.extract_entries("[![DOI](https://example.org/badge.svg)](https://doi.org/10.1234/test)")[0]

    def unavailable(*_args: object) -> dict[str, object]:
        message = "resolver unavailable"
        raise TimeoutError(message)

    assert MODULE.validate_entry(entry, 1.0, 0.45, unavailable).status == MODULE.AuditStatus.FAIL


SOFTWARE_DOI = "10.5281/zenodo.20033111"
SOFTWARE_TITLE = "markov-chain-monte-carlo: A composable MCMC framework for Rust"
CFF = f"""cff-version: 1.2.0
type: software
title: "{SOFTWARE_TITLE}"
doi: {SOFTWARE_DOI}
authors:
  - family-names: Getchell
    given-names: Adam
date-released: 2026-09-28
"""
SOFTWARE_LINKS = [
    f"[![DOI](https://zenodo.org/badge/DOI/{SOFTWARE_DOI}.svg)](https://doi.org/{SOFTWARE_DOI})",
    f"DOI: [{SOFTWARE_DOI}](https://doi.org/{SOFTWARE_DOI})",
    f"For software citation metadata, see [CITATION.cff](CITATION.cff). https://doi.org/{SOFTWARE_DOI}",
    f"- DOI: <https://doi.org/{SOFTWARE_DOI}>\n- Citation metadata: [CITATION.cff](CITATION.cff)",
    f"- DOI: <https://doi.org/{SOFTWARE_DOI}>\n- Citation metadata: [CITATION.cff][citation-metadata]",
]


def software_metadata() -> dict[str, object]:
    """Return the resolved software identity from the motivating issue."""
    return {**metadata(SOFTWARE_TITLE, family="Getchell", year=2026), "DOI": SOFTWARE_DOI}


@pytest.mark.parametrize("link", SOFTWARE_LINKS)
def test_software_link_requires_context_then_matches_explicit_cff(tmp_path: Path, link: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(link)[0]
    original = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata())
    assert original.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.OK
    assert result.local_status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.to_json_object()["canonical_software"]["doi"] == SOFTWARE_DOI
    assert original.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT


@pytest.mark.parametrize("claim", ["Wrong, A. " + SOFTWARE_TITLE + ". 2026.", "Getchell. Unrelated science. 2026.", "Getchell. " + SOFTWARE_TITLE + ". 2001."])
@pytest.mark.parametrize("link", SOFTWARE_LINKS[:2])
def test_canonical_software_never_overrides_local_contradictions(tmp_path: Path, claim: str, link: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(f"{claim}\n{link}")[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.canonical_software is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("DOI", "10.1234/wrong"), ("DOI", "invalid"), ("title", "Another work"), ("author", [{"family": "Wrong"}]), ("issued", {"date-parts": [[2001]]})],
)
def test_canonical_software_rejects_wrong_resolved_identity(tmp_path: Path, field: str, value: object) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    raw = {**software_metadata(), field: value}
    result = MODULE.validate_entry(MODULE.extract_entries(SOFTWARE_LINKS[0])[0], 1.0, 0.0, lambda *_: raw, citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.MISMATCH


def test_wrong_linked_doi_cannot_match_canonical_identity(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(SOFTWARE_LINKS[0].replace(SOFTWARE_DOI, "10.1234/wrong"))[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.MISMATCH


@pytest.mark.parametrize("field", ["DOI", "author", "issued"])
def test_incomplete_resolved_software_is_not_a_match(tmp_path: Path, field: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    raw = software_metadata()
    del raw[field]
    result = MODULE.validate_entry(MODULE.extract_entries(SOFTWARE_LINKS[0])[0], 1.0, 0.45, lambda *_: raw, citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "title: [broken",
        CFF.replace("type: software", "type: dataset"),
        CFF.replace("date-released: 2026-09-28", ""),
        CFF.replace("family-names: Getchell", "family-names: 123"),
        CFF.replace(f"doi: {SOFTWARE_DOI}", ""),
        CFF.replace("date-released: 2026-09-28", "date-released: unknown"),
    ],
)
def test_invalid_canonical_input_is_a_cli_error(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str) -> None:
    markdown, cff = tmp_path / "README.md", tmp_path / "CITATION.cff"
    markdown.write_text(SOFTWARE_LINKS[0])
    cff.write_text(content)
    assert MODULE.run([str(markdown), "--citation-cff", str(cff), "--json"]) == 2
    assert not capsys.readouterr().out


def test_canonical_cli_keeps_scholarly_checks_and_input_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    markdown, cff = tmp_path / "README.md", tmp_path / "CITATION.cff"
    markdown.write_text(SOFTWARE_LINKS[0] + "\n\nShewchuk. Robust predicates. 1997. DOI: [10.1234/paper](https://doi.org/10.1234/paper)\n")
    cff.write_text(CFF + 'preferred-citation:\n  title: "Unrelated preferred paper"\n')
    original = MODULE.validate_entries

    def fetcher(doi: Any, _timeout: float) -> dict[str, object]:
        return software_metadata() if str(doi.value) == SOFTWARE_DOI else metadata("Robust predicates")

    monkeypatch.setattr(MODULE, "validate_entries", lambda entries, timeout, score, **kwargs: original(entries, timeout, score, fetcher, **kwargs))
    assert MODULE.run([str(markdown), "--citation-cff", str(cff), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["status"] for row in rows] == ["OK", "OK"]
    assert rows[0]["local_status"] == "INSUFFICIENT_CONTEXT"
    assert "canonical_software" not in rows[1]
    assert rows[0]["source"]["path"] == str(markdown)


def test_empty_input_fails_without_allow_empty() -> None:
    """Empty audits fail loudly unless the caller opts out."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        path = Path(handle.name)
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            code = MODULE.run([str(path)])
    finally:
        path.unlink()

    assert code == 2
    assert "no DOI references found" in stderr.getvalue()


def test_invalid_threshold_is_rejected_by_argparse() -> None:
    """CLI parsing rejects non-finite title thresholds."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        path = Path(handle.name)
        handle.write("- Shewchuk. https://doi.org/10.1007/PL00009321\n")
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            try:
                MODULE.run(["--min-title-score", "nan", str(path)])
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            else:
                code = 0
    finally:
        path.unlink()

    assert code == 2
    assert "threshold must be" in stderr.getvalue()


TESTS = [
    test_extracts_doi_label_with_parentheses_and_angle_tokens,
    test_extracts_markdown_link_destination_with_balanced_parentheses,
    test_extracts_raw_url_with_trailing_period,
    test_validation_flags_author_mismatch,
    test_validation_accepts_matching_title_author_and_year,
    test_validation_reports_malformed_fetcher_response,
    test_empty_input_fails_without_allow_empty,
    test_invalid_threshold_is_rejected_by_argparse,
]


def main() -> int:
    """Run the fixture tests without requiring pytest."""
    for test in TESTS:
        test()
    print(f"Ran {len(TESTS)} tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
