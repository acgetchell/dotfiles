# Shared tooling adoption

The exact published `research-repo-tools` package owns reusable mechanics.
Dotfiles retains policy, machine provisioning, fixtures, and its skill protocols.
No sibling checkout or unreleased code is needed.

| Capability | Dotfiles adoption |
| --- | --- |
| Python baseline | `inherit-python = true`; `python-baseline-check` is part of `python-check` and CI |
| Python migration | `shared-python-plan VERSION` and `shared-python-update VERSION` run the target release through isolated uvx |
| File selection | Shared inventory and bounded batches for Python, Markdown, YAML, actionlint, and Semgrep |
| Python lint/type policy | Complete configured Ruff and ty checks over tracked/nonignored `.py` and `.pyi`, including fixtures; fixers retain the narrower safe scope |
| Workflow auditing | One locked Python zizmor pin and explicit persona; SHA pinning, offline local gate, required-online hosted audit, guarded SARIF upload; local YAML allowlist check reads the committed Actions settings |
| Dependency/secret scanning | Managed OSV/Gitleaks, explicit root `uv.lock`, full reachable history and current files, redacted reports; required CI `verify` includes the gate |
| Scanner lifecycle | `tools-sync`, `tools-check`, `update-security-tools`, and preview-first `clean`; package-owned cache store |
| Dependency/tool updates | Shared dependency and tool-pin helpers; Homebrew uv pin reconciliation; machine Cargo tools remain with their existing owner |
| Semgrep fixtures | Shared assertion runner over repository rules, syntax mutation pairs, and count expectations that retain path filters; integration tests exercise real review-graph source/test paths |
| Notebooks | Published inspection/advice/lint/cleanup/execution in the Jupyter skill; its consumer template prohibits dependency installs inside cells |
| Reviews | Shared opt-in CodeRabbit wrapper defaults to verified `origin/main`; no review is sent merely by running CI |
| Review-graph helpers | Direct public exact-byte hashing and subprocess APIs; graph serialization and immutable publication retain their protocol contracts |
| Dependabot | SHA-pinned v0.1.7 reusable workflow; hosted rollout is tracked in [the rollout guide](../.github/DEPENDABOT.md) |

## Python authority and upgrades

The installed release supplies its Python requirement and development minor.
`.python-version` and dependency-only `project.requires-python` are checked mirrors.
Ruff and ty have no duplicated Python target pins. CI reads the selector; the
host's unversioned Homebrew Python is independent of the uv project environment.

When upstream publishes the desired Python baseline, run:

```sh
just shared-python-plan VERSION
just shared-python-update VERSION
just ci
just security
```

Preview resolves a temporary candidate and may download packages or Python.
Apply updates all direct shared-package pins, both Python mirrors, the lockfile,
and the environment with upstream's recovery protocol. It runs outside the old
environment, so upgrading to Python 3.15 does not require editing dotfiles'
Python literals by hand. Publication alone does not change the pinned consumer.
Review the resulting diff and commit through the normal maintainer workflow.

The uv requirement is separate from Python inheritance. Its sole pin lives in
`[tool.uv].required-version`. The small Just bootstrap expression reads the
conventional assignment without needing Python, and `just update-uv` reconciles
it through the shared owner-aware updater. No local machine packages are
installed by ordinary validation.

## Scope decisions

`just github-actions-check` combines actionlint, `workflow-allowlist-check`, and
zizmor. The YAML allowlist checker reads `.github/settings/actions-selected.json`
for both action steps and reusable-workflow jobs. It supports the current exact
`owner/repo[/path]@*` entries and rejects unsupported policy forms rather than
silently widening access. Local and container actions remain outside this
external-repository allowlist; actionlint owns the complete workflow schema.
Zizmor owns SHA pinning. Its regular persona does not enforce the repository's
blanket `persist-credentials: false` policy, and its installed `forbidden-uses`
audit misses reusable-workflow calls, so these stricter checks retain local owners.
The generic allowlist checker is proposed for research-repo-tools v0.1.8 in
[upstream #66](https://github.com/acgetchell/research-repo-tools/issues/66).
[Dotfiles #105](https://github.com/acgetchell/dotfiles/issues/105) tracks adoption
and removal of the local checker after the published release supplies it.

Semgrep retains version-comment, locked-command, trigger, explicit checkout,
bootstrap, portability, and review-graph policies. The retired
`CODERABBIT_REVIEW_TOKEN` is forbidden in every workflow, including the approval
caller. The shared approval job uses `GITHUB_TOKEN`. Add mutation pairs for new
YAML forms and count assertions when a rule's path scope changes.

OSV scans the root Python lockfile. The embedded zero-dependency Rust warmup
fixture is deliberate review input, not a shipped Cargo product. Root Cargo
dependency upgrades, cargo-deny, Rust documentation snippet scans, scientific
validators, coverage summaries, benchmark-publication tooling, changelog
generation, and release metadata commands have no corresponding consumer
workflow here. Skill review benchmarks retain their domain-specific runners.

The shared Semgrep `files run` and fixture runner are used in the normal gate.
The per-input JSON/SARIF `semgrep scan` command is not substituted: it disables
`nosemgrep`, conflicts with the reviewed Dependabot trigger exception, and
requires every selected file to be scanned despite this repository's mixed
language and path-specific rules. Dotfiles retains only scan policy and temporary
cache/TLS setup, not a second file inventory or fixture implementation.

Full shared `setup` also installs user-wide Just and edits shell PATH. Dotfiles
already owns that machine provisioning through bootstrap/Homebrew/Cargo, so
`just setup` composes it with shared `toolchain sync` rather than introducing a
second owner. Managed scanner binaries and cleanup use the package's standard
`~/.cache/research-repo-tools` store. Supply `clean --keep-root PATH` for other
consumers sharing it. To use a custom store, set `RESEARCH_REPO_TOOLS_HOME` to an
absolute path. The store may be inside or outside the checkout.
v0.1.7 cleanup still rejects relative paths returned by uv's Python inventory;
this can occur even when the custom store path is absolute.

The Gitleaks policy keeps all default detectors. Two rule-specific exceptions
match only the exact `Validation/Test` routing label in the two review-routing
references and the historical `ABCDEF123456` README placeholder. Neither skips
a file or commit; other credentials in those locations still fail the scan.

`just ci` is the local validation tier. `just security` is the explicit
network/scanner tier, also required inside the hosted `verify` job;
`just security-check` remains a compatibility alias. Use `just security-osv` and
`just security-secrets` for individual scans. The dedicated
zizmor workflow tests authenticated online audits and upload permissions; a local
offline pass does not establish those hosted results.
