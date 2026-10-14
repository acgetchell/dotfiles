# Shared tooling adoption

The exact published `research-repo-tools==0.1.9` package owns reusable mechanics.
Dotfiles retains policy, machine provisioning, fixtures, and its skill protocols.
No sibling checkout or unreleased code is needed.

| Capability | Dotfiles adoption |
| --- | --- |
| Python baseline | `inherit-python = true`; shared `python check` validates the mirrors as part of CI; `python-baseline-check` remains available separately |
| Python migration | `shared-python-plan VERSION` and `shared-python-update VERSION` run the target release through isolated uvx |
| File selection | Shared inventory and bounded batches for Python, Markdown, YAML, actionlint, and Semgrep |
| Python lint/type policy | Complete configured Ruff and ty checks over tracked/nonignored `.py` and `.pyi`, including fixtures; fixers retain the narrower safe scope |
| Workflow auditing | One locked Python zizmor pin and explicit persona; SHA pinning, offline local gate, required-online hosted audit, guarded SARIF upload; shared Actions allowlist command reads the committed settings |
| Dependency/secret scanning | Managed OSV/Gitleaks, explicit root `uv.lock`, full reachable history and current files, redacted reports; required CI `verify` includes the gate |
| Scanner lifecycle | `tools-sync`, `tools-check`, `update-security-tools`, and preview-first `clean`; package-owned cache store |
| Dependency/tool updates | Shared helpers with a preflight guard for unsupported project overrides; Homebrew uv pin reconciliation; machine Cargo tools retain their existing owner |
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

The v0.1.9 adoption sets Python 3.15 as the floor. `just python-check` uses
the published `python check` pipeline: one complete inventory, then format,
lint, and strict ty checks with the first failing batch stopping the command.
`python-typecheck` uses the same shared owner. `python-fix` retains its narrower
scope to preserve deliberately invalid Semgrep fixtures.

Semgrep 1.180.0 pins `pywin32==311` on Windows, whose wheels stop at Python 3.14.
The Windows-only uv override selects 312, which publishes cp315 wheels. Remove
the override when Semgrep advances its dependency. Universal lock resolution
checks package availability; native Windows execution remains a hosted check.

The v0.1.9 direct-pin updater resolves through temporary PEP 723 metadata that
does not copy this project override. It can consequently downgrade Semgrep even
though the project lock resolves correctly. `update-python-dependencies` stops
before shared resolution while overrides are present. Use `uv lock --upgrade`
for a transitive refresh that retains direct pins and project overrides. For a
deliberate direct-pin change, use `uv add --dev 'PACKAGE==VERSION'`, review the
manifest/lock diff, and run `just ci` plus `just security`. Remove the preflight
guard after upstream supports overrides; the shared package remains the updater
owner. `just update` also stops at this guard during its Python dependency step.

Skill validation uses PyYAML's C safe loader when installed, with the Python
safe loader as a supported fallback. Explicit Python 3.15 lazy imports defer
CLI-only dependencies; the YAML merge marker uses a named `sentinel`, and fixed
review labels use `frozendict`. Graph JSON encoding and byte identities retain
their existing contracts. See [the adoption evaluation](python315-adoption.md)
for measurements and the limits of optional C-extension and JIT results.

The uv requirement is separate from Python inheritance. Its sole pin lives in
`[tool.uv].required-version`. The small Just bootstrap expression reads the
conventional assignment without needing Python, and `just update-uv` reconciles
it through the shared owner-aware updater. No local machine packages are
installed by ordinary validation.

## Scope decisions

`just github-actions-check` combines actionlint, `workflow-allowlist-check`, and
zizmor. The installed `research-repo-tools actions allowlist` command reads `.github/settings/actions-selected.json`
for both action steps and reusable-workflow jobs. It supports the current exact
`owner/repo[/path]@*` entries and rejects unsupported policy forms rather than
silently widening access. Local and container actions remain outside this
external-repository allowlist; actionlint owns the complete workflow schema.
Zizmor owns SHA pinning. Its regular persona does not enforce the repository's
blanket `persist-credentials: false` policy, which remains in Semgrep. The shared
allowlist command covers reusable-workflow calls independently of zizmor's
`forbidden-uses` audit.

The published checker replaces `scripts/check_workflow_allowlist.py` as part of
[dotfiles #105](https://github.com/acgetchell/dotfiles/issues/105). Generic YAML
parsing and malformed-policy regressions live in the
[upstream Actions tests](https://github.com/acgetchell/research-repo-tools/blob/v0.1.9/tests/dependencies/test_actions.py).
Dotfiles retains installed-package consumer tests for its actual workflows,
unapproved action and reusable-call mutations with file/line diagnostics,
committed policy authority, and recipe/CI wiring. The shared Dependabot workflow's
v0.1.7 commit pin is independent of this Python package migration.

Semgrep retains version-comment, locked-command, explicit checkout, bootstrap,
portability, safe skill YAML loading, selective Python runtime settings, and
review-graph policies. One locked-command rule now covers both `uv run` and
`uv sync`, replacing the duplicate workflow-only sync rule. Ruff and ty own
general Python syntax, lint, and type checks; zizmor owns SHA pinning and
dangerous workflow triggers. The retired
`CODERABBIT_REVIEW_TOKEN` is forbidden in every workflow, including the approval
caller. The shared approval job uses `GITHUB_TOKEN`. Add mutation pairs for new
YAML forms and count assertions when a rule's path scope changes. Python 3.15
fixtures cover unsafe C/Python loader selection and global lazy-import settings;
the production-path matrix also checks imported aliases and test exclusions.

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
Shared cleanup still rejects relative paths returned by uv's Python inventory;
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
