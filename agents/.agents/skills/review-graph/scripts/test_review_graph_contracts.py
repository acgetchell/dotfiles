"""Prompt budgets and semantic routing guards collected before graph execution."""

import json
from pathlib import Path

import pytest
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import expand_compact_routing, load_routing_catalog, plan_from_document, validate_routing_ledger
from review_graph_runtime import build_routing_projection_document
from test_support_review_graph import ROUTING_CATALOG, SKILL_ROOT, VALIDATOR_CONTRACT, VALIDATOR_SKILL, _assessed_fixture_candidates, _sparse_plan_document
from test_support_review_graph_capture import _capture, _commit_all, _git, _init_repo

pytestmark = pytest.mark.review_contract

ORDINARY_PROMPT_WORD_BUDGET = 2400

VALIDATOR_PROMPT_WORD_BUDGET = 850

ALL_SURFACE_PROMPT_WORD_BUDGET = 4200

TRACE_PRIORITIZED_RUST_LEAF_BUDGETS = {
    "rust-api-design": 1400,
    "rust-api-docs": 950,
    "rust-cargo-hygiene": 900,
    "rust-error-variants": 1400,
    "rust-invariant-performance": 1350,
    "rust-prelude-exports": 950,
    "rust-production-review": 950,
    "rust-scientific-correctness": 1500,
    "rust-test-quality": 950,
}

TRACE_PRIORITIZED_DOCUMENTATION_SKILL_BUDGETS = {
    "academic-authorship-boundary": 700,
    "cpp-api-docs": 950,
    "docs-review-orchestrator": 400,
    "repository-docs-review": 800,
    "scientific-citation-audit": 500,
    "scientific-crate-docs-review": 750,
    "scientific-software-docs-review": 900,
}

TRACE_PRIORITIZED_PYTHON_SKILL_BUDGETS = {
    "jupyter-notebook-review": 900,
    "python-api-design": 1100,
    "python-build-portability": 1050,
    "python-cli-review": 800,
    "python-parse-dont-validate": 850,
    "python-production-review": 1100,
    "python-review-orchestrator": 400,
    "python-scientific-review": 750,
    "python-support-scripts": 800,
    "python-test-quality": 800,
}

TRACE_PRIORITIZED_SHARED_SKILL_BUDGETS = {"project-tooling-review": 850}

ALL_SURFACE_PATHS = (
    "src/lib.cpp",
    "include/lib.hpp",
    "src/lib.rs",
    "src/main.py",
    "docs/README.md",
    "justfile",
    "pyproject.toml",
    "Cargo.toml",
    "CMakeLists.txt",
)

ALL_ROUTER_IDS = ("review-graph", "cpp-review-orchestrator", "rust-review-orchestrator", "python-review-orchestrator", "docs-review-orchestrator")


def _word_count(paths: tuple[Path, ...]) -> int:
    """Count whitespace-delimited words across the UTF-8 documents in the instruction budget."""
    return sum(len(path.read_text(encoding="utf-8").split()) for path in paths)


@pytest.mark.parametrize(
    ("path", "router"),
    [
        ("src/lib.rs", "rust-review-orchestrator"),
        ("include/api.hpp", "cpp-review-orchestrator"),
        ("src/app.py", "python-review-orchestrator"),
        ("README.md", "docs-review-orchestrator"),
    ],
)
def test_path_matches_require_semantic_assessment_before_planning(path: str, router: str) -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    with pytest.raises(ValueError, match="semantic applicability decisions required"):
        expand_compact_routing(catalog, consulted_routers=["review-graph", router], captured_paths=[path], overrides=[])


@pytest.mark.parametrize(
    ("path", "router", "missing_catalog_id"),
    [
        ("src/app.py", "python-review-orchestrator", "python.parse"),
        ("src/api.pyi", "python-review-orchestrator", "python.api-design"),
        ("scripts/check.py", "python-review-orchestrator", "python.style"),
        ("src/api.pyi", "python-review-orchestrator", "python.style"),
        ("README.md", "docs-review-orchestrator", "docs.repository"),
    ],
)
def test_partial_assessment_reports_the_remaining_candidate(path: str, router: str, missing_catalog_id: str) -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    routers = ["review-graph", router]
    assessments = _assessed_fixture_candidates([path], routers, {})
    assert any(entry["catalog_id"] == missing_catalog_id for entry in assessments)
    partial_assessments = [entry for entry in assessments if entry["catalog_id"] != missing_catalog_id]
    assert partial_assessments

    with pytest.raises(ValueError, match="semantic applicability decisions required") as error:
        expand_compact_routing(catalog, consulted_routers=routers, captured_paths=[path], overrides=partial_assessments)

    assert str(error.value) == f"semantic applicability decisions required for path-matched candidates: {missing_catalog_id}"


def test_markdown_only_capture_routes_fenced_python_to_style_review(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    guide = repo / "guide.md"
    guide.write_text("Prose.\n")
    _commit_all(repo)
    guide.write_text("> - ~~~Python\n>   print(42)\n>   ~~~\n")
    _git(repo, "add", "guide.md")
    guide.write_text("````text\n```python\n```\n````\n")
    template = _sparse_plan_document()
    template.update(
        consulted_routers=["review-graph"],
        routing_overrides=[],
        concrete_change_target=True,
        change_target="git diff --cached -- guide.md",
        scope_mode="staged-only",
    )
    template["validation_requirements"][0]["working_directories"] = [str(repo)]
    for mode, selected in (("staged", True), ("worktree", False)):
        capture = _capture(repo, mode)
        document = bootstrap_document(capture, template)
        projection = build_routing_projection_document(document)
        assert ("python-review-orchestrator" in projection["consulted_routers"]) == selected
        if selected:
            assert next(entry for entry in projection["entries"] if entry["catalog_id"] == "python.style")["matched_paths"] == ["guide.md"]
            plan = plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repo)
            assert plan.dispatch_allowed, plan.blockers
            style = next(node for node in plan.actual_worker_nodes if node.skill_id == "python-style-hygiene")
            assert style.coverage == ("guide.md",)


def test_markdown_example_preserves_explicit_style_assessment_for_python_source() -> None:
    paths = ["guide.md", "tool.py"]
    routers = ["review-graph", "python-review-orchestrator"]
    assessments = _assessed_fixture_candidates(paths, routers, {})
    with pytest.raises(ValueError, match=r"required for path-matched candidates: python\.style$"):
        expand_compact_routing(
            load_routing_catalog(ROUTING_CATALOG),
            consulted_routers=routers,
            captured_paths=paths,
            python_example_paths=["guide.md"],
            overrides=[item for item in assessments if item["catalog_id"] != "python.style"],
        )


def test_sparse_routing_expands_to_exhaustive_catalog_records() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    decisions = expand_compact_routing(
        catalog,
        consulted_routers=("review-graph", "rust-review-orchestrator"),
        captured_paths=("src/lib.rs",),
        overrides=_assessed_fixture_candidates(
            ["src/lib.rs"],
            ["review-graph", "rust-review-orchestrator"],
            {"rust.errors": "Only typed error propagation changed; no shared state or scheduling contract"},
        ),
        change_target="git diff origin/main...HEAD",
    )

    assessment = validate_routing_ledger(catalog, decisions, consulted_routers=("review-graph", "rust-review-orchestrator"))
    by_id = {decision.catalog_id: decision for decision in decisions}
    assert assessment.feasible
    assert len(decisions) == sum(entry.router_id in {"review-graph", "rust-review-orchestrator"} for entry in catalog)
    assert by_id["repo.rust"].disposition == "selected"
    assert by_id["rust.errors"].skill_id == "rust-error-variants"
    assert by_id["rust.errors"].disposition == "selected"
    assert by_id["rust.concurrency"].disposition == "not-applicable"
    assert {item.catalog_id for item in decisions if item.disposition == "selected"} == {
        "repo.rust",
        "repo.independent",
        "repo.synthesis",
        "rust.errors",
        "rust.synthesis",
    }
    assert by_id["rust.concurrency"].review_surface == ("src/lib.rs",)
    assert by_id["rust.synthesis"].disposition == "selected"


def test_sparse_routing_rejects_catalog_owned_identity_fields() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    with pytest.raises(ValueError, match="catalog-owned fields"):
        expand_compact_routing(
            catalog,
            consulted_routers=("review-graph", "rust-review-orchestrator"),
            captured_paths=("src/lib.rs",),
            overrides=(
                {
                    "applicability_evidence": ["typed errors changed"],
                    "catalog_id": "rust.errors",
                    "disposition": "selected",
                    "reason": "typed errors changed",
                    "review_surface": ["src/lib.rs"],
                    "skill_id": "substituted-skill",
                },
            ),
        )


def test_routing_projection_is_complete_compact_and_hashed() -> None:
    captured_path = "src/lib.rs"
    projection = build_routing_projection_document(
        {"captured_paths": [captured_path], "consulted_routers": ["review-graph", "rust-review-orchestrator"]},
        catalog_path=ROUTING_CATALOG,
        skill_roots=(SKILL_ROOT,),
    )

    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    expected_ids = {entry.catalog_id for entry in catalog if entry.router_id in {"review-graph", "rust-review-orchestrator"}}
    projected = {entry["catalog_id"]: entry for entry in projection["entries"]}
    assert set(projected) == expected_ids
    assert projected["rust.errors"]["matched_paths"] == [captured_path]
    assert projected["rust.concurrency"]["matched_paths"] == [captured_path]
    assert projection["projection_digest"].startswith("sha256:")


def test_routing_regression_fixtures_enforce_selected_and_excluded_ownership() -> None:
    fixture = Path(__file__).with_name("fixtures") / "routing_regressions.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]

    for case in cases:
        projection = build_routing_projection_document(
            {"captured_paths": case["paths"], "consulted_routers": case["consulted_routers"]}, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)
        )
        projected = {entry["catalog_id"]: entry for entry in projection["entries"]}
        for catalog_id, expected_matches in case["expected_matches"].items():
            assert projected[catalog_id]["matched_paths"] == expected_matches, case["id"]
        catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
        decisions = expand_compact_routing(
            catalog,
            consulted_routers=case["consulted_routers"],
            captured_paths=case["paths"],
            overrides=_assessed_fixture_candidates(case["paths"], case["consulted_routers"], {}),
        )
        decisions_by_id = {decision.catalog_id: decision for decision in decisions}
        # Projection fixtures deliberately consult extra routers to test exclusions.
        assert set(decisions_by_id) == {entry.catalog_id for entry in catalog if entry.router_id in case["consulted_routers"]}
        for catalog_id, expected_matches in case["expected_matches"].items():
            decision = decisions_by_id[catalog_id]
            assert decision.review_surface == tuple(expected_matches), case["id"]
            assert decision.disposition == ("selected" if catalog_id == "repo.tooling" and expected_matches else "not-applicable"), case["id"]


@pytest.mark.parametrize(
    ("paths", "router"),
    [
        (["justfile", "README.md"], "docs-review-orchestrator"),
        (["justfile", "CMakePresets.json"], "cpp-review-orchestrator"),
        (["tooling/examples.toml", "README.md"], "docs-review-orchestrator"),
    ],
)
@pytest.mark.parametrize("explicit_scope", [False, True])
def test_tooling_scope_combines_classifier_and_projection_unless_overridden(paths: list[str], router: str, explicit_scope: bool) -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    reason = "Targeted tooling scope; shared contracts have their own selected specialist"
    overrides = (
        [{"catalog_id": "repo.tooling", "disposition": "selected", "reason": reason, "applicability_evidence": [reason], "review_surface": paths[:1]}]
        if explicit_scope
        else []
    )
    routers = ["review-graph", router]
    overrides.extend(_assessed_fixture_candidates(paths, routers, {}))
    decisions = expand_compact_routing(catalog, consulted_routers=routers, captured_paths=paths, overrides=overrides)
    tooling = next(decision for decision in decisions if decision.catalog_id == "repo.tooling")
    expected = paths[:1] if explicit_scope else paths
    assert tooling.disposition == "selected"
    assert set(tooling.review_surface) == set(expected)
    assert len(tooling.review_surface) == len(expected)
    assert validate_routing_ledger(catalog, decisions, consulted_routers=routers).feasible


@pytest.mark.parametrize(
    ("catalog_id", "path", "reason"),
    [
        ("python.cli", "tests/fixtures/generate_ess.py", "Fixture utility exposes substantial argument validation and a versioned JSON output contract"),
        (
            "docs.scientific-software",
            "benches/diagnostic_backends/Cargo.lock",
            "Changed numerical backend dependency is evidence for a documented precision claim",
        ),
    ],
)
def test_projection_exclusions_preserve_semantic_overrides(catalog_id: str, path: str, reason: str) -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    language_router = "python-review-orchestrator" if path.endswith(".py") else "rust-review-orchestrator"
    routers = ["review-graph", language_router, "docs-review-orchestrator"]
    decisions = expand_compact_routing(
        catalog,
        consulted_routers=routers,
        captured_paths=[path, "README.md"],
        overrides=[
            *[item for item in _assessed_fixture_candidates([path, "README.md"], routers, {}) if item["catalog_id"] != catalog_id],
            {"catalog_id": catalog_id, "disposition": "selected", "reason": reason, "applicability_evidence": [reason], "review_surface": [path]},
        ],
    )
    decision = next(item for item in decisions if item.catalog_id == catalog_id)
    assert decision.disposition == "selected"
    assert decision.review_surface == (path,)
    assert validate_routing_ledger(catalog, decisions, consulted_routers=routers).feasible


def test_ordinary_validator_and_all_surface_prompt_budgets() -> None:
    review_prompt = (
        SKILL_ROOT / "repo-review" / "SKILL.md",
        SKILL_ROOT / "review-graph" / "SKILL.md",
        SKILL_ROOT / "review-graph" / "references" / "runtime-contract.md",
    )
    validator_prompt = (VALIDATOR_SKILL, VALIDATOR_CONTRACT)
    projection = build_routing_projection_document(
        {"captured_paths": list(ALL_SURFACE_PATHS), "consulted_routers": list(ALL_ROUTER_IDS)}, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)
    )
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    ordinary_words = _word_count(review_prompt)
    validator_words = _word_count(validator_prompt)
    projection_words = len(json.dumps(projection, indent=2, sort_keys=True).split())
    all_surface_words = ordinary_words + projection_words

    assert len(projection["entries"]) == len(catalog)
    assert set(projection["classifier_signals"]) == {"cpp", "documentation", "python", "rust", "tooling"}
    assert ordinary_words <= ORDINARY_PROMPT_WORD_BUDGET, f"ordinary coordinator prompt proxy is {ordinary_words} words"
    assert validator_words <= VALIDATOR_PROMPT_WORD_BUDGET, f"validator prompt proxy is {validator_words} words"
    assert all_surface_words <= ALL_SURFACE_PROMPT_WORD_BUDGET, f"all-surface prompt proxy is {all_surface_words} words"


@pytest.mark.parametrize(
    "budgets",
    [
        pytest.param(TRACE_PRIORITIZED_RUST_LEAF_BUDGETS, id="rust"),
        pytest.param(TRACE_PRIORITIZED_DOCUMENTATION_SKILL_BUDGETS, id="documentation"),
        pytest.param(TRACE_PRIORITIZED_PYTHON_SKILL_BUDGETS, id="python"),
        pytest.param(TRACE_PRIORITIZED_SHARED_SKILL_BUDGETS, id="shared"),
    ],
)
def test_trace_prioritized_prompt_budgets(budgets: dict[str, int]) -> None:
    for skill_id, budget in budgets.items():
        entrypoint = SKILL_ROOT / skill_id / "SKILL.md"
        words = _word_count((entrypoint,))

        assert words <= budget, f"{skill_id} graph/orchestrator entrypoint is {words} words"
