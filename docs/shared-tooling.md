# Shared tooling adoption

The exact published `research-repo-tools==0.2.5` package owns reusable mechanics.
Dotfiles retains policy, machine provisioning, fixtures, and its skill protocols.
No sibling checkout or unreleased code is needed.

| Capability | Dotfiles adoption |
| --- | --- |
| Python baseline | `inherit-python = true`; shared `python check` validates the mirrors as part of CI; `python-baseline-check` remains available separately |
| Python migration | `shared-python-plan VERSION` and `shared-python-update VERSION` run the target release through isolated uvx |
| File selection | Shared inventory and bounded batches for Python, Markdown, YAML, actionlint, and Semgrep |
| Python lint/type policy | Complete configured Ruff and ty checks over tracked/nonignored `.py` and `.pyi`, including fixtures; fixers retain the narrower safe scope |
| Workflow auditing | One locked Python zizmor pin and explicit persona; SHA pinning, offline local gate, required-online hosted audit, guarded SARIF upload; shared Actions allowlist command reads the committed settings |
| Dependency/secret scanning | Managed OSV/Gitleaks, explicit root/scanner locks, full reachable history and current files, redacted reports; required CI `verify` includes the gate |
| Scanner lifecycle | `tools-sync`, `tools-check`, `update-security-tools`, and preview-first `clean`; package-owned cache store |
| Dependency/tool updates | Shared `deps update-python --all-projects` for the root and explicitly declared scanner; Homebrew uv pin reconciliation; machine Cargo tools retain their existing owner |
| Semgrep fixtures | Shared assertion runner over repository rules, syntax mutation pairs, and count expectations that retain path filters; integration tests exercise real review-graph source/test paths |
| Notebooks | Published inspection/advice/lint/cleanup/execution in the Jupyter skill; its consumer template prohibits dependency installs inside cells |
| Reviews | Shared opt-in CodeRabbit wrapper defaults to verified `origin/main`; no review is sent merely by running CI |
| Review-graph helpers | Public exact-byte hashing, subprocess, and index-preserving status/diff APIs; graph serialization and immutable publication retain their protocol contracts |
| Dependabot | SHA-pinned v0.1.8 reusable workflow; hosted rollout is tracked in [the rollout guide](../.github/DEPENDABOT.md) |

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

Native scan recipes retain Semgrep 1.182.1's independent Python 3.14 environment
in `tooling/semgrep`. Its own manifest retains the
Windows `pywin32==312` override and the patched `mcp>=1.30.0,<2` constraint.
It also uses OpenTelemetry 1.45.1/0.66b1 for
[GHSA-xcq7-p3pf-p88h](https://github.com/advisories/GHSA-xcq7-p3pf-p88h).
The v0.2.5 shared fixture runner requires Semgrep 1.182.1 in its own Python 3.15
environment. The root dev group therefore requests `research-repo-tools[semgrep]`
and carries the published compatibility constraints, including Windows pywin32,
patched MCP, and the consistent OpenTelemetry family. The tooling-only group
keeps the base package. Both scanner installations require wheels because the
source distribution lacks the native engine. The root also retains the
`rust-just==1.59.0` override, aligned with `just_version`.

`just update-python-dependencies` selects Homebrew uv and invokes the published
`deps update-python --all-projects` command. It updates root development pins,
upgrades both locks and synchronizes their separate environments. Only
`tooling/semgrep` is listed in `deps.python-projects`; notebook skill assets are
consumer templates and are never discovered or synchronized as projects.
`just python-sync` restores both locked environments. Native scan recipes pass
the configured scanner's absolute executable path. Shared fixture checks select the root
environment's absolute scanner entry point. Linux provisioning
keeps it in a separate `semgrep-venv` beneath `DOTFILES_REVIEW_PREFIX`, selected
through `DOTFILES_SEMGREP_ENVIRONMENT`, without replacing the main environment.
The Windows engine smoke selects the scanner project directly and requires one
expected finding from a local rule and fixture, with no scanner errors. This
configured check still needs native Windows evidence for the current changes.
`just security-osv` scans both locks.
The obsolete override-detection preflight has been removed. Each successful
project update remains applied if a later project fails; inspect the diff and
retry the same recipe after resolving the failure.

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
[upstream Actions tests](https://github.com/acgetchell/research-repo-tools/blob/v0.2.3/tests/dependencies/test_actions.py).
Dotfiles retains installed-package consumer tests for its actual workflows,
unapproved action and reusable-call mutations with file/line diagnostics,
committed policy authority, and recipe/CI wiring. The shared Dependabot workflow's
v0.1.8 commit pin is independent of this Python package migration.

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

OSV scans the root and independent scanner Python lockfiles. The embedded zero-dependency Rust warmup
fixture is deliberate review input, not a shipped Cargo product. Root Cargo
dependency upgrades, cargo-deny, Rust documentation snippet scans, scientific
validators, coverage summaries, benchmark-publication tooling, changelog
generation, and release metadata commands have no corresponding consumer
workflow here. Skill review benchmarks retain their domain-specific runners.

The shared Semgrep `files run` and fixture runner are used in the normal gate.
The shared `semgrep scan` command is not substituted: its complete scan-coverage
contract differs from this repository's mixed-language and path-specific rules.
The existing native scan retains reviewed inline suppressions. Dotfiles retains only scan policy and temporary
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

## v0.2.5 Git inspection adoption

The publication gate is the [upstream verification record for #170](https://github.com/acgetchell/research-repo-tools/issues/170#issuecomment-6607734141).
It records exact release revision `a66f34ceb62258ec3ad02658be00b4940429674d`,
successful native Linux/macOS/Windows and isolated distribution checks, both
PyPI distributions, and a clean normal-resolution consumer installation.
`just shared-python-plan 0.2.5` and `just shared-python-update 0.2.5` resolved the
published package and updated the root pin/lock; Python remains 3.15.
The initial full gate exposed the new shared-fixture scanner requirement;
requesting its published dev extra and applying the shared migration resolved it.
Consumer allowlist assertions follow the [published 0.2.5 diagnostics](https://github.com/acgetchell/research-repo-tools/blob/v0.2.5/src/research_repo_tools/workflow_allowlist.py):
the exact denied reference and missing approved identity, with source locations,
policy authority, failure status, and input preservation still checked. The
native scanner smoke selects an available `/etc/ssl/cert.pem` CA bundle when the
caller has not supplied one; its engine initializes TLS even for offline scans.

The wheel SHA-256 in `uv.lock` is
`5f2c000cba366f7c4c123e12e3b5eb9ebb24b4f8404392982e8b2cf271ba10fb`;
the sdist SHA-256 is
`554c59e188ac42eb86b9871ced2c6b0b69c1bd9fe390c75ea4a995e408f7b758`.
Both match the upstream publication record. No editable, Git/path, sibling, or
site-packages override supplies this adoption.

Scope capture uses the supported `research_repo_tools.git_inspect` status and
changed-path functions with 30-second deadlines. The shared helper owns
optional-lock/index-refresh suppression, literal paths, diff-driver overrides,
NUL bytes, content-based selection, and error/timeout transport. Its status
reports renames as deletion/addition. Ordinary metadata/object queries retain
their bounded literal byte runner; its defaults are not an inspection policy.
Dotfiles retains all four capture modes, path normalization, raw source
identities, provenance, frozen-helper isolation, and repair/staging ownership.
Commit verification uses the same shared status observation. Reconciliation
classifies shared Git failures as stale captures while retaining diagnostics.

Capture now avoids unused per-file index queries for regular files and symlinks.
Line bounds read tree/index inventories once per source side and exact immutable
blobs in batches of at most 64 objects. The two scope content observations remain
independent; source bytes, modes, symlink targets, selection, and index state are
read anew on every invocation. No stat-based or cross-capture cache is introduced.
See [capture phase profiling](../agents/.agents/skills/review-graph/references/dispatch-overhead.md#source-capture-phases-253)
for measurements and diagnostic commands.

Local and hosted validation for the adoption revision are separate: existing
native CI remains required, including Linux portable review and its graph
publication/final-proof smoke. Record the exact commit/run/attempt in the PR;
local macOS results do not establish hosted Linux or Windows validation.

## Historical v0.2.3 adoption evidence

The dependency is the published PyPI wheel recorded by URL and SHA-256 in
`uv.lock`; no local wheel, editable sibling or source override is used.
The scanner lock independently records Semgrep 1.182.1 and its dependencies.
The upstream publication prerequisite is [research-repo-tools #124](https://github.com/acgetchell/research-repo-tools/issues/124).

The locally exercised wheel identities are:

| Package | Wheel | SHA-256 |
| --- | --- | --- |
| research-repo-tools 0.2.3 | `research_repo_tools-0.2.3-py3-none-any.whl` | `da5f0259027662e7706b7f2b8a38d8e1f1d8a5dce314e2c996177b2947514fc6` |
| Semgrep 1.182.1 | macOS arm64, Python 3.10–3.14 | `89fe0afe240455800f806145f5679707892ea9bbd442a56eab1ea0b25a95f4c6` |

Local adoption exercised `just update-python-dependencies` through the published
all-projects updater, followed by locked scanner resolution at 1.182.1. The root
uses Python 3.15.1 and the scanner Python 3.14.7. Semgrep scans and rule fixtures,
Python lint/type checks, and both OSV lockfile scans plus Gitleaks passed on macOS.

Dotfiles has no Python or Rust registry release pipeline. Validated release
artifact promotion and registry-release instructions are therefore not applicable;
this adoption does not add a release pipeline. Review evidence remains local for
the review's duration. Required hosted checks remain the native repository CI
matrix, Linux setup/check/smoke, timing/Windows entry point and security gates.
A local pass does not establish those hosted results; record their exact commit,
run and attempt in the adoption PR once it exists.
