# Audit Execution Context And Reuse

Read when reporting execution facts, validation limits, or uncertainty in an
audit payload.

Classify audit context explicitly; never suppress a truthful caveat to gain reuse:

| Field | Meaning | Reuse effect |
| --- | --- | --- |
| `execution_facts` | Known attestations: `validators-not-executed`, `source-captures-match`, `git-not-mutated` | Informational; checked for contradictions with dispatched validator commands and supplied mutation/capture facts |
| `validation_limits` | Environment and reason bound to an explicit `validation_requirements` ID; status `delegated`, `unavailable`, or `failed` | Delegated evidence remains validator-owned; unavailable/failed evidence blocks audit reuse |
| `scope_limitations` | Exact omitted owned paths and reasons | Blocks reuse |
| `unresolved_uncertainties` | `kind` (`semantic` or `dependency`) and reason | Blocks reuse |
| Unit `dependency_uncertainty` | Unresolved dependency of one coverage unit | Rechecks that unit |
| `limitations` | Unclassified free-text caveats | Conservatively blocks reuse |

Unknown execution facts are rejected. `validators-not-executed` cannot coexist
with a ledger entry for a dispatched validator command. The ledger still records
inspection and artifact-publication commands; these facts neither supply
validation evidence nor remove planned checks. For example, a fresh worker that inspected
`tool.py` and the nearby `pyproject.toml`, with validators assigned elsewhere,
can publish this payload (substitute the actual dispatched paths):

```json
{
  "status": "no-findings",
  "files_inspected": ["tool.py"],
  "nearby_contract_owners": ["pyproject.toml"],
  "findings": [],
  "validation_requirements": [],
  "handoffs": [],
  "changes": [],
  "commands_executed": ["cat tool.py pyproject.toml"],
  "command_policy_attested": true,
  "limitations": [],
  "scope_limitations": [],
  "execution_facts": ["validators-not-executed", "git-not-mutated"],
  "coverage_units": [{
    "unit_id": "cli-contract",
    "owned_paths": ["tool.py"],
    "dependency_paths": ["pyproject.toml"],
    "dependency_uncertainty": "",
    "finding_indices": []
  }]
}
```
