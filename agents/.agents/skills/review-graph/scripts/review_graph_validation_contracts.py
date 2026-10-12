"""Repository-owned execution contracts and native Git input bindings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from review_graph_git_objects import GitPathIdentity
from review_graph_reuse import ReviewSourceSnapshot, regular_file_fingerprint

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

CONTRACT_PATH = "review-validation-contracts.json"
CONTRACT_VERSION = 1


class InputScope(StrEnum):
    """Repository inputs are broad unless a reviewed contract narrows them."""

    REPOSITORY = "repository"
    PREFIXES = "prefixes"


class ContractGitInput(StrEnum):
    """Git values observable by a contracted check."""

    INDEX = "index"
    HEAD = "head"
    HISTORY = "history"
    COMPARISON = "comparison"


def object_fields(raw: object, label: str, *, required: set[str], optional: AbstractSet[str] = frozenset()) -> dict[str, object]:
    """Reject missing or unknown boundary fields with a useful diagnostic."""
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        msg = f"{label} must be an object with string keys"
        raise TypeError(msg)
    data: dict[str, object] = {key: value for key, value in raw.items() if isinstance(key, str)}
    if required - data.keys() or data.keys() - required - optional:
        msg = f"{label} has missing or unsupported fields: {sorted(required - data.keys())}, {sorted(data.keys() - required - optional)}"
        raise ValueError(msg)
    return data


def texts(raw: object, label: str) -> tuple[str, ...]:
    """Parse immutable, nonempty string elements."""
    if not isinstance(raw, (tuple, list)) or any(not isinstance(item, str) or not item.strip() for item in raw):
        msg = f"{label} must be an array of nonempty strings"
        raise ValueError(msg)
    return tuple(item for item in raw if isinstance(item, str))


def repository_path(raw: str) -> str:
    """Require portable repository-relative path selection."""
    if not raw or "\0" in raw or raw.startswith("/") or "\\" in raw or PurePosixPath(raw).as_posix() != raw or {".", ".."} & set(raw.split("/")):
        msg = f"contract path must be repository-relative: {raw!r}"
        raise ValueError(msg)
    return raw


def _require_git_inputs(raw: object) -> None:
    if not isinstance(raw, tuple) or any(not isinstance(item, ContractGitInput) for item in raw):
        msg = "contract git_inputs must be typed immutable categories"
        raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class CheckContract:
    """Exact execution and reviewed dependency policy; workers cannot weaken it."""

    contract_id: str
    commands: tuple[str, ...]
    working_directories: tuple[str, ...]
    implementation_paths: tuple[str, ...]
    input_scope: InputScope
    input_prefixes: tuple[str, ...]
    git_inputs: tuple[ContractGitInput, ...]
    deterministic: bool
    rationale: str

    def __post_init__(self) -> None:
        """Keep direct construction as strict as JSON parsing."""
        if not isinstance(self.contract_id, str) or not self.contract_id.strip() or not isinstance(self.rationale, str) or not self.rationale.strip():
            msg = "check contract requires an ID and dependency rationale"
            raise ValueError(msg)
        for label, values in (
            ("commands", self.commands),
            ("working_directories", self.working_directories),
            ("implementation_paths", self.implementation_paths),
            ("input_prefixes", self.input_prefixes),
        ):
            if not isinstance(values, tuple):
                msg = f"contract {label} must be an immutable tuple"
                raise TypeError(msg)
            texts(values, f"contract {label}")
        if not self.commands or len(self.commands) != len(self.working_directories) or not self.implementation_paths:
            msg = "contract requires exact command/directory pairs and implementation paths"
            raise ValueError(msg)
        for path in (*self.implementation_paths, *self.input_prefixes):
            repository_path(path)
        if any(directory != "." and repository_path(directory) != directory for directory in self.working_directories):
            msg = "contract working directories must be repository-relative"
            raise ValueError(msg)
        if not isinstance(self.input_scope, InputScope) or bool(self.input_prefixes) != (self.input_scope == InputScope.PREFIXES):
            msg = "prefix input scope requires nonempty input prefixes; repository scope requires none"
            raise ValueError(msg)
        _require_git_inputs(self.git_inputs)
        if len(set(self.git_inputs)) != len(self.git_inputs) or type(self.deterministic) is not bool:
            msg = "contract Git inputs must be unique and deterministic must be boolean"
            raise ValueError(msg)

    @classmethod
    def from_raw(cls, raw: object) -> CheckContract:
        """Parse the complete standard contract, with no legacy alternatives."""
        data = object_fields(raw, "check contract", required=set(cls.__dataclass_fields__))
        contract_id, rationale, deterministic = data["contract_id"], data["rationale"], data["deterministic"]
        if not isinstance(contract_id, str) or not isinstance(rationale, str) or not isinstance(deterministic, bool):
            msg = "contract ID/rationale/deterministic have invalid types"
            raise TypeError(msg)
        return cls(
            contract_id,
            texts(data["commands"], "commands"),
            texts(data["working_directories"], "working_directories"),
            texts(data["implementation_paths"], "implementation_paths"),
            InputScope(data["input_scope"]),
            texts(data["input_prefixes"], "input_prefixes"),
            tuple(ContractGitInput(item) for item in texts(data["git_inputs"], "git_inputs")),
            deterministic,
            rationale,
        )

    def matches_execution(self, *, repository_root: Path, commands: tuple[str, ...], working_directories: tuple[str, ...]) -> bool:
        """Match exact execution without treating an isolated directory as malformed."""
        if commands != self.commands:
            return False
        directories = tuple((Path(directory) if Path(directory).is_absolute() else repository_root / directory) for directory in working_directories)
        if any(not directory.is_relative_to(repository_root) for directory in directories):
            return False
        relative = tuple("." if directory == repository_root else directory.relative_to(repository_root).as_posix() for directory in directories)
        return relative == self.working_directories

    def selected_inputs(self, snapshot: ReviewSourceSnapshot) -> tuple[tuple[str, str], ...]:
        """Bind selection membership too, including newly added and removed paths."""
        roots = (*self.input_prefixes, *self.implementation_paths, CONTRACT_PATH)
        directory_links = {
            link
            for link in snapshot.repository_symlink_paths
            if any(directory == link or directory.startswith(link + "/") for directory in self.working_directories)
        }
        return tuple(
            (path, identity)
            for path, identity in snapshot.repository_path_fingerprints
            if identity != "absent"
            and (self.input_scope == InputScope.REPOSITORY or path in directory_links or any(path == root or path.startswith(root + "/") for root in roots))
        )


@dataclass(frozen=True, slots=True)
class ContractBinding:
    """Original contract bytes proven against the captured native Git blob."""

    registry_content: str
    registry_identity: str
    contract: CheckContract

    def __post_init__(self) -> None:
        """Retain verified registry membership, including direct construction."""
        if not isinstance(self.registry_content, str) or not isinstance(self.registry_identity, str) or not isinstance(self.contract, CheckContract):
            msg = "contract binding requires typed immutable fields"
            raise TypeError(msg)
        identity = GitPathIdentity.parse(self.registry_identity)
        if (
            identity.mode not in {"100644", "100755"}
            or regular_file_fingerprint(CONTRACT_PATH, self.registry_content.encode(), executable=identity.mode == "100755", algorithm=identity.algorithm)
            != self.registry_identity
        ):
            msg = "contract registry bytes differ from its captured Git blob"
            raise ValueError(msg)
        if self.contract not in parse_contracts(json.loads(self.registry_content)):
            msg = "check contract is not declared in its bound registry"
            raise ValueError(msg)

    def verify_inputs(self, snapshot: ReviewSourceSnapshot) -> None:
        """Bind registry and implementation objects to the verified original capture."""
        identities = dict(snapshot.repository_path_fingerprints)
        if identities.get(CONTRACT_PATH) != self.registry_identity:
            msg = "validation contract registry differs from original captured inputs"
            raise ValueError(msg)
        for path in self.contract.implementation_paths:
            identity = identities.get(path, "absent")
            if (
                not identity.startswith("git:")
                or GitPathIdentity.parse(identity).mode not in {"100644", "100755"}
                or any(path == link or path.startswith(link + "/") for link in snapshot.repository_symlink_paths)
            ):
                msg = "contract implementation paths require captured regular Git blobs without symlink traversal"
                raise ValueError(msg)

    def to_document(self) -> dict[str, object]:
        """Export passive immutable transport at the serialization boundary."""
        return {
            "registry_content": self.registry_content,
            "registry_identity": self.registry_identity,
            "contract": {
                "contract_id": self.contract.contract_id,
                "commands": list(self.contract.commands),
                "working_directories": list(self.contract.working_directories),
                "implementation_paths": list(self.contract.implementation_paths),
                "input_scope": self.contract.input_scope.value,
                "input_prefixes": list(self.contract.input_prefixes),
                "git_inputs": [item.value for item in self.contract.git_inputs],
                "deterministic": self.contract.deterministic,
                "rationale": self.contract.rationale,
            },
        }

    @classmethod
    def from_raw(cls, raw: object) -> ContractBinding:
        """Parse a retained binding without reading a newer working tree registry."""
        data = object_fields(raw, "contract binding", required={"registry_content", "registry_identity", "contract"})
        content, identity = data["registry_content"], data["registry_identity"]
        if not isinstance(content, str) or not isinstance(identity, str):
            msg = "contract registry content/identity must be strings"
            raise TypeError(msg)
        return cls(content, identity, CheckContract.from_raw(data["contract"]))


def parse_contracts(raw: object) -> tuple[CheckContract, ...]:
    """Reject unknown versions and ambiguous execution contracts."""
    data = object_fields(raw, "check contract registry", required={"schema_version", "contracts"})
    if type(data["schema_version"]) is not int or data["schema_version"] != CONTRACT_VERSION:
        msg = "unsupported check contract registry version; expected 1"
        raise ValueError(msg)
    values = data["contracts"]
    if not isinstance(values, list):
        msg = "check contract registry contracts must be an array"
        raise TypeError(msg)
    contracts = tuple(CheckContract.from_raw(value) for value in values)
    if len({contract.contract_id for contract in contracts}) != len(contracts) or len(
        {(contract.commands, contract.working_directories) for contract in contracts}
    ) != len(contracts):
        msg = "check contract IDs and execution selections must be unique"
        raise ValueError(msg)
    return contracts


def load_contract_binding(snapshot: ReviewSourceSnapshot, commands: tuple[str, ...], working_directories: tuple[str, ...]) -> ContractBinding | None:
    """Resolve exact commands from repository-owned, captured registry bytes."""
    snapshot.verify()
    identities = dict(snapshot.repository_path_fingerprints)
    identity = identities.get(CONTRACT_PATH)
    if identity is None or identity == "absent":
        return None
    root = Path(snapshot.repository_root)
    path = root / CONTRACT_PATH
    if path.is_symlink() or not path.is_file():
        msg = "check contract registry must be a captured regular file"
        raise ValueError(msg)
    content = path.read_bytes().decode("utf-8")
    contracts = parse_contracts(json.loads(content))
    match = next(
        (contract for contract in contracts if contract.matches_execution(repository_root=root, commands=commands, working_directories=working_directories)),
        None,
    )
    if match is None:
        return None
    binding = ContractBinding(content, identity, match)
    binding.verify_inputs(snapshot)
    return binding
