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
| Workflow auditing | One locked Python zizmor pin and explicit persona; offline local gate, required-online hosted audit, guarded SARIF upload |
| Dependency/secret scanning | Managed OSV/Gitleaks, explicit root `uv.lock`, full reachable history and current files, redacted reports; required CI `verify` includes the gate |
| Scanner lifecycle | `tools-sync`, `tools-check`, `update-security-tools`, and preview-first `clean`; package-owned cache store |
| Dependency/tool updates | Shared dependency and tool-pin helpers; Homebrew uv pin reconciliation; machine Cargo tools remain with their existing owner |
| Semgrep fixtures | Shared assertion runner over repository rules and deliberate positive/negative fixtures |
| Notebooks | Published inspection/advice/lint/cleanup/execution in the Jupyter skill; its consumer template prohibits dependency installs inside cells |
| Reviews | Shared opt-in CodeRabbit wrapper; no review is sent merely by running CI |
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
just security-check
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
consumers sharing it. v0.1.7 cleanup rejects relative paths in uv's Python
inventory, so keep a custom store outside the checkout.

The Gitleaks policy keeps all default detectors. Two rule-specific exceptions
match only the exact `Validation/Test` routing label in the two review-routing
references and the historical `ABCDEF123456` README placeholder. Neither skips
a file or commit; other credentials in those locations still fail the scan.

`just ci` is the local validation tier. `just security-check` is the explicit
network/scanner tier, also required inside the hosted `verify` job. The dedicated
zizmor workflow tests authenticated online audits and upload permissions; a local
offline pass does not establish those hosted results.
