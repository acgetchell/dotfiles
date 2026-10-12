"""Validation requirement parsing proves its contract without capturing a repository."""

import subprocess
from copy import deepcopy
from typing import Any, cast

import pytest
from review_graph_plan import ValidationRequirement, validation_requirements_from_document
from test_support_review_graph import _sparse_plan_document


@pytest.fixture(autouse=True)
def no_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pure parsing scenario must not acquire live source state or launch tools."""

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("validation parsing unexpectedly launched a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)


def _validation_document() -> dict[str, Any]:
    return {"validation_requirements": _sparse_plan_document()["validation_requirements"]}


def test_validation_requirements_return_typed_values_without_mutating_input() -> None:
    document = _validation_document()
    before = deepcopy(document)

    requirements = validation_requirements_from_document(document, repository_root=None)

    assert len(requirements) == 1
    requirement = requirements[0]
    assert isinstance(requirement, ValidationRequirement)
    assert requirement.requirement_id == "baseline-validation"
    assert requirement.source_state == ("scope", "worktree", "repository")
    assert requirement.commands == ("true",)
    assert requirement.working_directories == tuple(document["validation_requirements"][0]["working_directories"])
    assert requirement.required is True
    assert requirement.baseline is True
    assert document == before


@pytest.mark.parametrize("value", ["false", 0, 1, None])
@pytest.mark.parametrize("field", ["required", "baseline"])
def test_validation_requirements_reject_non_boolean_flags(field: str, value: object) -> None:
    document = _validation_document()
    document["validation_requirements"][0][field] = value
    before = deepcopy(document)

    with pytest.raises(ValueError, match="must be a boolean"):
        validation_requirements_from_document(document, repository_root=None)

    assert document == before


@pytest.mark.parametrize(
    "source_state", ["scope", ["scope", "worktree"], ["scope", "worktree", "repository", "extra"], ["scope", " ", "repository"], ["scope", 1, "repository"]]
)
def test_validation_requirements_reject_malformed_source_state(source_state: object) -> None:
    document = _validation_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation["source_state"] = source_state
    before = deepcopy(document)

    with pytest.raises(ValueError, match="source_state must be exactly three bounded non-empty strings"):
        validation_requirements_from_document(document, repository_root=None)

    assert document == before


@pytest.mark.parametrize(
    "field",
    [
        "requirement_id",
        "environment",
        "toolchain",
        "platform",
        "artifact_owner",
        "mutation_lock",
        "request",
        "requested_scope",
        "capture_command",
        "authority",
        "selection_reason",
        "mutation_classification",
        "expected_evidence",
        "elapsed_time_budget",
        "dependency_policy",
        "execution_strategy",
        "independence_basis",
    ],
)
def test_validation_requirements_reject_non_string_configuration(field: str) -> None:
    document = _validation_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation[field] = True
    before = deepcopy(document)

    with pytest.raises(ValueError, match=rf"{field} must be a bounded non-empty string"):
        validation_requirements_from_document(document, repository_root=None)

    assert document == before


@pytest.mark.parametrize("value", [1, [], {}, None, " "])
def test_validation_requirements_reject_malformed_configuration_text(value: object) -> None:
    document = _validation_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation["environment"] = value
    before = deepcopy(document)

    with pytest.raises(ValueError, match="environment must be a bounded non-empty string"):
        validation_requirements_from_document(document, repository_root=None)

    assert document == before
