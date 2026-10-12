"""Contracts reject weak declarations and preserve exact portable Git bindings."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from review_graph_reuse import regular_file_fingerprint
from review_graph_schema import require_schema
from review_graph_validation_contracts import CONTRACT_PATH, CheckContract, ContractBinding, InputScope, parse_contracts


def _contract() -> dict[str, object]:
    return {
        "contract_id": "fixture",
        "commands": ["just check"],
        "working_directories": ["."],
        "implementation_paths": ["justfile"],
        "input_scope": "repository",
        "input_prefixes": [],
        "git_inputs": [],
        "deterministic": True,
        "rationale": "Checks captured source with the bound environment.",
    }


@pytest.mark.parametrize("version", [None, True, "1", 2])
def test_registry_rejects_missing_weak_or_unsupported_versions(version: object) -> None:
    registry: dict[str, object] = {"contracts": [_contract()]}
    if version is not None:
        registry["schema_version"] = version
    with pytest.raises(ValueError, match=r"unsupported check contract registry version|missing or unsupported fields"):
        parse_contracts(registry)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "path/../escape", "bad\0path", "path\\file"])
def test_contract_rejects_nonportable_input_paths(path: str) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        CheckContract.from_raw({**_contract(), "implementation_paths": [path]})


def test_registry_rejects_ambiguous_selections_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unique"):
        parse_contracts({"schema_version": 1, "contracts": [_contract(), {**_contract(), "contract_id": "another"}]})
    with pytest.raises(ValueError, match="unsupported fields"):
        CheckContract.from_raw({**_contract(), "worker_override": True})
    with pytest.raises(TypeError, match="deterministic"):
        CheckContract.from_raw({**_contract(), "deterministic": 1})


def test_direct_contract_replacements_cannot_weaken_immutable_invariants() -> None:
    contract = CheckContract.from_raw(_contract())
    with pytest.raises(TypeError, match="immutable"):
        replace(contract, commands=["just check"])
    with pytest.raises(ValueError, match="prefix input scope"):
        replace(contract, input_scope=InputScope.PREFIXES)


@pytest.mark.parametrize("algorithm", ["sha1", "sha256"])
@pytest.mark.parametrize("executable", [False, True])
def test_registry_binding_preserves_crlf_bytes_and_git_modes(algorithm: str, executable: bool) -> None:
    content = json.dumps({"schema_version": 1, "contracts": [_contract()]}, indent=2).replace("\n", "\r\n")
    identity = regular_file_fingerprint(CONTRACT_PATH, content.encode(), executable=executable, algorithm=algorithm)
    binding = ContractBinding(content, identity, CheckContract.from_raw(_contract()))
    assert ContractBinding.from_raw(binding.to_document()) == binding
    with pytest.raises(ValueError, match="captured Git blob"):
        replace(binding, registry_content=content + " ")


def test_repository_registry_matches_the_published_schema() -> None:
    root = Path(__file__).resolve().parents[5]
    registry = json.loads((root / CONTRACT_PATH).read_bytes())
    require_schema(registry, Path(__file__).resolve().parents[1] / "references" / "schemas" / "check-contracts-v1.schema.json")
    assert len(parse_contracts(registry)) == 3
    assert all((root / path).is_file() for contract in parse_contracts(registry) for path in contract.implementation_paths)


def test_isolated_directory_is_unmatched_and_historical_matching_does_not_follow_live_symlinks(tmp_path: Path) -> None:
    contract = CheckContract.from_raw({**_contract(), "working_directories": ["nested"]})
    assert not contract.matches_execution(repository_root=tmp_path, commands=contract.commands, working_directories=(str(tmp_path.parent),))
    (tmp_path / "nested").symlink_to(tmp_path.parent, target_is_directory=True)
    assert contract.matches_execution(repository_root=tmp_path, commands=contract.commands, working_directories=(str(tmp_path / "nested"),))
