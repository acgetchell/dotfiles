#!/usr/bin/env python3
"""Fixture tests for validate_reference_dois.py."""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

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
