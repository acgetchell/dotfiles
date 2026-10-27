"""Filename discovery is neither conclusion access nor source-read evidence."""

import json
from pathlib import Path

import pytest
import review_graph_runtime as runtime
from review_graph_isolation import IsolationPublicationError, isolation_violations
from review_graph_reads import path_only_inventory, source_read_operands
from test_review_graph_runtime import _compact_audit_payload, _worker_input_fixture


@pytest.mark.parametrize(
    "template",
    ["rg --files {root} -g '*audit-024*' -g '*execution.json'", "ls -la {root}", "ls -l {peer}", "rg --files --glob='*.json' {root}", "rg --files -- {peer}"],
)
def test_filename_inventory_publishes_without_claiming_reads(tmp_path: Path, template: str) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "audit")
    peer = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "validation")
    command = template.format(root=Path(audit["worker_input_path"]).parent, peer=peer["metadata_path"])
    assert path_only_inventory(command)
    assert source_read_operands(command) is None
    payload = _compact_audit_payload(audit, commands=(command,))
    assert isolation_violations(audit["dispatch"], payload) == ()
    contract = json.loads(Path(audit["worker_payload_contract_path"]).read_bytes())
    content = json.dumps(payload).encode()
    assert runtime.publish_worker_payload_bytes(contract, content)["status"] == "published"
    assert Path(audit["worker_payload_path"]).read_bytes() == content
    assert not list(Path(audit["worker_payload_path"]).parent.glob("*.isolation-rejected.*.json"))
    view = json.loads(Path(audit["worker_execution_path"]).read_bytes())
    assert view["self_dispatch_recovery"]["worker_execution_path"] == audit["worker_execution_path"]
    assert view["self_dispatch_recovery"]["worker_input_path"] == view["canonical_input"]["path"]


@pytest.mark.parametrize("command", ["rg --files .", "ls -l tool.py"])
def test_inventory_cannot_satisfy_source_inspection(tmp_path: Path, command: str) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "audit")
    payload = _compact_audit_payload(audit, commands=(command,))
    payload["files_inspected"] = []
    contract = json.loads(Path(audit["worker_payload_contract_path"]).read_bytes())
    with pytest.raises(ValueError, match=r"files_inspected|inspection of every owned path"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert not Path(audit["worker_payload_path"]).exists()


@pytest.mark.parametrize(
    "template",
    [
        "rg --files {root} | xargs cat",
        "rg --files {root}; cat {peer}",
        "ls {root} && cat {peer}",
        "ls $(cat {peer})",
        "ls `cat {peer}`",
        "rg --files -f {peer} {root}",
        "rg --files --pre 'cat {peer}' {root}",
        "rg --files-with-matches . {root}",
        "rg -- --files {peer}",
        "find {root} -exec cat {{}} \\;",
    ],
)
def test_content_access_is_not_laundered_as_inventory(tmp_path: Path, template: str) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "audit")
    peer = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "validation")
    command = template.format(root=Path(audit["worker_input_path"]).parent, peer=peer["metadata_path"])
    assert not path_only_inventory(command)
    contract = json.loads(Path(audit["worker_payload_contract_path"]).read_bytes())
    content = json.dumps(_compact_audit_payload(audit, commands=(command,))).encode()
    with pytest.raises(IsolationPublicationError) as failure:
        runtime.publish_worker_payload_bytes(contract, content)
    assert Path(failure.value.receipt["rejected_payload"]["path"]).read_bytes() == content
    assert not Path(audit["worker_payload_path"]).exists()
