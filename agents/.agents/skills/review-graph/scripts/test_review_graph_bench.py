"""Benchmark proof commands keep build, fixture, timing, and argument semantics."""

import json
import shlex
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from review_graph_bench import benchmark_identity, benchmark_recipes, equivalent_recipe
from review_graph_plan import ValidationRequirement
from review_graph_runtime import _expanded_validation_plan, _late_validation_quality_blockers
from test_review_graph_runtime import _compile_materialized_evidence, _late_validation_plan, _late_validation_requirement


@pytest.mark.parametrize(
    "command",
    [
        "cargo build --package bench",
        "cargo --config bench build",
        "cargo +nightly -Z unstable-options -C bench build",
        "cargo --color bench",
        "cargo --help bench",
        "cargo --unknown bench",
    ],
)
def test_non_benchmark_subcommands_and_option_values_are_not_benchmarks(command: str) -> None:
    assert benchmark_identity(command) is None


@pytest.mark.parametrize(
    "context",
    [
        "cargo",
        "cargo +nightly -Z unstable-options -C bench",
        "cargo --config bench --color never -vv --locked",
        "cargo --config=bench --color=never -Zunstable-options -Cbench",
    ],
)
def test_global_options_preserve_the_actual_benchmark_subcommand(context: str) -> None:
    identity = benchmark_identity(context + " bench --bench interval -- --test")
    assert identity is not None
    assert identity.cargo_context == tuple(shlex.split(context))
    assert identity.targets == ("interval",)
    assert identity.harness_arguments == ("--test",)


@pytest.mark.parametrize("attribute", ["[windows]", "[unix]", "[no-cd]", '[working-directory: "bench"]'])
def test_unproven_execution_attributes_do_not_require_recipes(tmp_path: Path, attribute: str) -> None:
    (tmp_path / "justfile").write_text(f"{attribute}\n# Recipe context must still be observed.\nbench-interval:\n    cargo bench --bench interval\n")
    assert benchmark_recipes(tmp_path) == {}


def test_global_just_execution_settings_do_not_prove_equivalence(tmp_path: Path) -> None:
    (tmp_path / "justfile").write_text('set working-directory := "other"\nbench-interval:\n    cargo bench --bench interval\n')
    assert benchmark_recipes(tmp_path) == {}


@pytest.mark.parametrize("argument", ["match filter", "", "*.rs", "$(touch marker)", "value; true", "~", "#comment"])
def test_raw_just_forwarding_rejects_arguments_that_need_shell_quoting(tmp_path: Path, argument: str) -> None:
    (tmp_path / "justfile").write_text("bench-interval *args:\n    cargo bench --bench interval -- {{args}}\n")
    requested = benchmark_identity("cargo bench --bench interval -- " + shlex.quote(argument))
    assert requested is not None
    assert equivalent_recipe(requested, benchmark_recipes(tmp_path)["bench-interval"], "bench-interval") is None


def test_forwarding_equivalence_matches_real_just_expansion(tmp_path: Path) -> None:
    just = shutil.which("just")
    assert just is not None
    path = tmp_path / "justfile"
    path.write_text("bench-interval *args:\n    cargo bench --bench interval -- {{args}}\n")
    requested = benchmark_identity("cargo bench --bench interval -- --test --sample-size 10")
    assert requested is not None
    equivalent = equivalent_recipe(requested, benchmark_recipes(tmp_path)["bench-interval"], "bench-interval")
    assert equivalent is not None
    result = subprocess.run(  # noqa: S603 - installed Just only prints the fixed fixture's expansion.
        [just, "--justfile", str(path), "--dry-run", *shlex.split(equivalent)[1:]], capture_output=True, text=True, check=True
    )
    assert benchmark_identity(result.stderr.strip()) == requested


@pytest.mark.parametrize("argument", ["$BENCH_FILTER", "*.rs", "$(printf filter)", "~"])
@pytest.mark.parametrize("variadic", [False, True])
def test_shell_expansion_differences_do_not_require_literal_or_forwarding_recipes(tmp_path: Path, argument: str, variadic: bool) -> None:
    base = "cargo bench --bench interval -- "
    suffix = " --test" if variadic else ""
    parameter = " *args" if variadic else ""
    forwarding = " {{args}}" if variadic else ""
    body = base + shlex.quote(argument) + forwarding
    (tmp_path / "justfile").write_text(f"bench-interval{parameter}:\n    {body}\n")
    requested = benchmark_identity(base + argument + suffix)
    assert requested is not None
    assert equivalent_recipe(requested, benchmark_recipes(tmp_path)["bench-interval"], "bench-interval") is None
    requirement = ValidationRequirement(
        "fixtures", ("s", "w", "r"), (base + argument + suffix,), (str(tmp_path),), "native", "stable", (), "native", "validator", "serial"
    )
    assert _late_validation_quality_blockers(requirement, repository_root=tmp_path, authorization="review-only") == ()


def test_shell_expansion_does_not_bypass_required_cargo_features(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[[bench]]\nname="interval"\nrequired-features=["bench"]\n')
    command = "cargo bench --bench interval -- $BENCH_FILTER"
    requirement = ValidationRequirement("fixtures", ("s", "w", "r"), (command,), (str(tmp_path),), "native", "stable", (), "native", "validator", "serial")
    assert any(
        "missing required features: bench" in item
        for item in _late_validation_quality_blockers(requirement, repository_root=tmp_path, authorization="review-only")
    )


@pytest.mark.parametrize(
    ("suffix", "mode", "canonical"),
    [("", "timing", True), (" --no-run", "build-only", False), (" -- --test", "test", False), (" -- --sample-size 10", "timing", False)],
)
def test_parameterless_timing_recipe_preserves_other_modes(tmp_path: Path, suffix: str, mode: str, canonical: bool) -> None:
    (tmp_path / "Cargo.toml").write_text('[[bench]]\nname = "linear_form"\nrequired-features = ["bench"]\n')
    (tmp_path / "justfile").write_text("bench-linear-form:\n    cargo bench --locked --features bench --bench linear_form\n")
    command = "cargo bench --locked --features bench --bench linear_form" + suffix
    identity = benchmark_identity(command)
    assert identity is not None
    assert identity.mode == mode
    requirement = ValidationRequirement("fixtures", ("s", "w", "r"), (command,), (str(tmp_path),), "native", "stable", (), "native", "validator", "serial")
    blockers = _late_validation_quality_blockers(requirement, repository_root=tmp_path, authorization="review-only")
    assert bool(blockers) == canonical
    missing = replace(requirement, commands=(command.replace(" --features bench", ""),))
    assert any(
        "missing required features" in item for item in _late_validation_quality_blockers(missing, repository_root=tmp_path, authorization="review-only")
    )


@pytest.mark.parametrize(
    ("body", "suffix", "expected"),
    [
        (" -- {{args}}", " -- --test", "just bench-interval --test"),
        (" {{ args }}", " --no-run", "just bench-interval --no-run"),
        (" {{args}}", " -- --test", "just bench-interval -- --test"),
    ],
)
def test_forwarding_recipe_requires_exact_forwarded_behavior(tmp_path: Path, body: str, suffix: str, expected: str) -> None:
    command = "cargo bench --locked --features bench --bench interval"
    (tmp_path / "justfile").write_text(f"bench-interval *args:\n    {command}{body}\n")
    requirement = ValidationRequirement(
        "fixtures", ("s", "w", "r"), (command + suffix,), (str(tmp_path),), "native", "stable", (), "native", "validator", "serial"
    )
    blockers = _late_validation_quality_blockers(requirement, repository_root=tmp_path, authorization="review-only")
    assert any(expected in blocker for blocker in blockers)
    assert (
        _late_validation_quality_blockers(
            replace(requirement, commands=(expected,), canonical_recipe=expected), repository_root=tmp_path, authorization="review-only"
        )
        == ()
    )


def test_multiple_targets_keep_all_feature_obligations_and_exact_command(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[[bench]]\nname="interval"\nrequired-features=["bench"]\n[[bench]]\nname="linear_form"\nrequired-features=["linear"]\n'
    )
    (tmp_path / "justfile").write_text("bench-linear-form:\n    cargo bench --bench linear_form --features bench,linear\n")
    command = "cargo bench --features bench --bench interval --bench=linear_form -- --test"
    requirement = ValidationRequirement("fixtures", ("s", "w", "r"), (command,), (str(tmp_path),), "native", "stable", (), "native", "validator", "serial")
    assert any(
        "linear_form is missing required features: linear" in item
        for item in _late_validation_quality_blockers(requirement, repository_root=tmp_path, authorization="review-only")
    )
    complete = replace(requirement, commands=(command.replace("--features bench", "--features bench,linear"),))
    assert _late_validation_quality_blockers(complete, repository_root=tmp_path, authorization="review-only") == ()
    assert complete.commands[0].endswith("-- --test")


def test_required_forwarding_parameter_cannot_replace_argumentless_timing(tmp_path: Path) -> None:
    command = "cargo bench --features bench --bench interval"
    (tmp_path / "justfile").write_text(f"bench-interval +args:\n    {command} -- {{{{args}}}}\n")
    requested = benchmark_identity(command)
    assert requested is not None
    assert equivalent_recipe(requested, benchmark_recipes(tmp_path)["bench-interval"], "bench-interval") is None


def test_criterion_fixture_requirement_expands_on_unchanged_review_epoch(tmp_path: Path) -> None:
    commands = [f"cargo bench --locked --features bench --bench {target} -- --test" for target in ("interval", "linear_form")]
    (tmp_path / "Cargo.toml").write_text(
        '[[bench]]\nname="interval"\nrequired-features=["bench"]\n[[bench]]\nname="linear_form"\nrequired-features=["bench"]\n'
    )
    (tmp_path / "justfile").write_text(
        "bench-interval:\n    cargo bench --locked --features bench --bench interval\n"
        "bench-linear-form:\n    cargo bench --locked --features bench --bench linear_form\n"
    )
    discovery = {
        **_late_validation_requirement(),
        "requirement_id": "rust-tests-benchmark-fixtures",
        "commands": commands,
        "working_directory": str(tmp_path),
        "reason": "CI compiles harnesses without executing their fixture assertions",
    }
    plan, sources = _compile_materialized_evidence(tmp_path / "proof", late_requirements=[discovery])
    records = [json.loads(Path(source["metadata_path"]).read_text())["normalized_record"] for source in sources]
    requirement = {
        **_late_validation_plan(),
        "requirement_id": discovery["requirement_id"],
        "commands": commands,
        "working_directories": [str(tmp_path)] * 2,
        "request": discovery["reason"],
        "captured_paths": [],
    }
    expanded = _expanded_validation_plan(
        {"source_state": ["scope", "worktree", "repository"], "validation_requirements": [requirement]}, plan, records, tmp_path, authorization="review-only"
    )
    unit = next(unit for unit in expanded.coalesced_validation_units if discovery["requirement_id"] in unit.requirement_ids)
    assert unit.commands == tuple(commands)
    assert unit.source_state == ("scope", "worktree", "repository")
    assert expanded.coalesced_validation_units[: len(plan.coalesced_validation_units)] == plan.coalesced_validation_units
    altered = {**requirement, "commands": [commands[0].replace("-- --test", ""), commands[1]]}
    with pytest.raises(ValueError, match="canonical recipe"):
        _expanded_validation_plan(
            {"source_state": ["scope", "worktree", "repository"], "validation_requirements": [altered]}, plan, records, tmp_path, authorization="review-only"
        )
