#!/usr/bin/env python3
"""Fixture tests for validate_reference_dois.py."""

# ruff: noqa: S101

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("validate_reference_dois.py")
SPEC = importlib.util.spec_from_file_location("validate_reference_dois", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
if SPEC.loader is None:
    message = "validate_reference_dois.py could not be loaded"
    raise RuntimeError(message)
SPEC.loader.exec_module(MODULE)


def metadata(title: str, *, family: str = "Shewchuk", year: int = 1997) -> dict[str, object]:
    """Return a minimal CSL-shaped metadata fixture."""
    return {
        "title": title,
        "author": [{"family": family, "given": "J. R."}],
        "issued": {"date-parts": [[year]]},
        "container-title": "Fixture Journal",
    }


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
            "Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates",
            family="Shewchuk",
            year=1997,
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
            "Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates",
            family="Shewchuk",
            year=1997,
        ),
    )

    assert result.status == MODULE.AuditStatus.OK


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
                code = int(exc.code)
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
