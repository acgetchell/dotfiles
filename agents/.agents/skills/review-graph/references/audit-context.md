# Audit Execution Context And Reuse

Read when reporting execution facts, validation limits, or uncertainty in an
audit payload.

Fresh audits cannot read another node's input, payload, report, or evidence,
including CI evidence. Validation remains delegated through planned requirement
references. Own-node contracts, raw source, supplied shared source packets, and
explicitly inherited coverage references are permitted. Predecessor IDs grant
no broader reading permission. The compact view and worker prompt carry this
boundary; publication and compilation check truthful read/command ledgers.

Classify audit context explicitly; never suppress a truthful caveat to gain reuse:

| Field | Meaning | Reuse effect |
| --- | --- | --- |
| `execution_facts` | Known attestations: `validators-not-executed`, `source-captures-match`, `git-not-mutated` | Informational; checked for contradictions with dispatched validator commands and supplied mutation/capture facts |
| `validation_limits` | Environment and reason bound to an explicit `validation_requirements` ID; status `delegated`, `unavailable`, or `failed` | Delegated/unavailable evidence remains validator-owned and blocks readiness when unfulfilled; failed evidence reopens its owning contract after source/dependency assessment |
| `scope_limitations` | Exact omitted owned paths and reasons | Blocks reuse |
| `unresolved_uncertainties` | `kind` (`semantic` or `dependency`) and reason | Blocks reuse |
| Unit `dependency_uncertainty` | Unresolved dependency of one coverage unit | Rechecks that unit |
| `limitations` | Unclassified free-text caveats | Conservatively blocks reuse |

For external staging, declare `git_dependencies` separately from execution
caveats: distinguish diff-based `source-discovery` from `index`, `head`, or
`history` judgments. See [state transitions](state-transitions.md) for the
command binding, unchanged-read proof, and conservative legacy behavior.

Materialized audit and independent inputs provide `provenance_examples` fragments
using owned and context paths. They are illustrative, never evidence of performed
work. Merge actual reads and commands, covering every owned path; replace the
illustrative `origin/main` with the captured base. Keep each Git invocation in a
separate `commands_executed` entry, and copy its exact text into the declaration.
Plain `git diff`, optionally with `HEAD`, `--cached`/`--staged`, and
`-- relative/path`, supports `source-discovery` when judgments depend only on
captured source reads. Other revision diffs, such as `git diff origin/main`, use
conservative `head`; use `index` or `history` for those semantic dependencies.
Compound commands cannot be declared `source-discovery`.

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

## Instruction And Recipe Changes

Complete fresh audits retain the full bytes of applicable repository instructions.
For recipe dependencies, a coverage unit may additionally declare
`"recipe_dependencies": [{"path": "justfile", "recipes": ["check"]}]`. Name the
recipes actually inspected, including dependencies and relevant shared settings;
the path must be in `dependency_paths`. This retains full recipe-document bytes
and permits focused semantic review of a later delta; the declaration alone
never establishes irrelevance.

After a repair, `instruction-review` coverage units have unchanged owned source
and other dependencies, but changed instruction/recipe documents. Their compact
views include exact changed sections and both complete file identities. Full
before/after text stays in the bound proof. Missing text, changed modes, symlinks,
changed source, uncertain dependencies, or changed instruction applicability
remain full rechecks.

A **fresh audit worker** inspects every changed section against its contract and
submits `instruction_reconciliations`, using the payload schema's optional shape.
Each unit assesses every changed document and records actual reads in
`nearby_contract_owners`. For each document, `rules`, `commands`, `applicability`,
and `obligations` each contain `changed` and a concrete `reason`.
`changed_sections_inspected` must be true. Disposition `unchanged` is permitted
only when every dimension is unchanged; it retains original findings and source
evidence. `reinspect` requires fresh inspection of every owned path in that unit.
`uncertain` requires blocked status. Omission performs the full source recheck.
Coordinators cannot submit reconciliation waivers. Never decide irrelevance from
a filename or from the preserved source alone.

The compiler replays both source captures, complete document bytes and the
original coverage proof at publication and acceptance. It binds the new semantic
judgment to its worker payload and preserves original validation obligations and
handoffs. Independent final review, scientific checks, validator ownership,
native CI requirements, and the two-batch boundary continue unchanged.
