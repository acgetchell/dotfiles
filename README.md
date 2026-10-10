# My Dotfiles

Personal macOS dotfiles managed with [GNU Stow](https://www.gnu.org/software/stow/) and [Homebrew Bundle](https://github.com/Homebrew/homebrew-bundle),
plus Linux cloud/HPC development and review tooling installed in user-owned directories.

This repo is intended to remain public. Committed files define reproducible, non-secret defaults; machine-specific values live in local ignored files such as `~/.zshrc.local`, `~/.gitconfig.local`, and `Brewfile.local`.

## Layout

Each top-level directory is a stow package. Package contents mirror paths under `$HOME`.

```text
dotfiles/
├── Brewfile                # foundational formulae + casks
├── justfile                # local setup, stow, and CI recipes
├── pyproject.toml          # uv-managed Python tooling
├── semgrep.yaml            # repository-owned guardrail rules
├── bin/
│   ├── bootstrap.sh        # fresh-machine provisioner
│   ├── macos-defaults.sh   # captured macOS preferences (defaults write)
│   └── verify.sh           # health check / sanity check
├── scripts/
│   ├── skill_validate.py   # Codex skill metadata checks
│   └── stow_verify.py      # stow symlink integrity checker
├── tests/
│   └── semgrep/            # Semgrep rule fixtures
├── git/
│   └── .gitconfig          # stows to ~/.gitconfig
├── zsh/
│   └── .zshrc              # stows to ~/.zshrc
└── agents/
    └── .agents/
        ├── AGENTS.md       # stows to ~/.agents/AGENTS.md
        └── skills/         # stows to ~/.agents/skills/
            └── */SKILL.md
```

## Platform scope

| Environment | Scope | Verification status |
| --- | --- | --- |
| macOS | Desktop dotfiles, Homebrew, Stow, full repository checks | Existing native CI; new Linux installer is separate |
| Linux x86_64, glibc >= 2.28 | User-space review tools and full portable checks | Ubuntu 24.04 CI and Debian 13.6 cloud checks passed; other distributions unverified |
| Linux aarch64, glibc >= 2.28 | Same provisioning candidate | Native validation unverified |
| Cara's cloud computer | Debian 13.6 x86_64 portable review environment | Setup, repeat setup, full checks, scripted smoke, and fresh restore verified; actual coordinator/worker review outstanding |
| HPC | Site modules, scratch, authorized execution placement | Cluster configuration and native execution unverified |
| Windows | Portable timing helper | Timing CI only; full tooling setup unsupported |

Linux support covers development/review tooling. The macOS shell, Git dotfile,
desktop preferences, and Homebrew setup have not been ported to Linux.
See the [Linux/cloud/HPC guide](docs/linux-review-environment.md) for prerequisites,
offline execution, evidence, and separate cloud/cluster verification.
The guide records the [2026-10-05 verification evidence](docs/linux-review-environment.md#evidence-and-verification-status)
and the remaining actual-cloud review criterion, transferred from
[#95](https://github.com/acgetchell/dotfiles/issues/95) to
[#123](https://github.com/acgetchell/dotfiles/issues/123). Scripted graph smoke
does not establish a completed multi-agent review. TypeSafe access is not an
environment acceptance requirement following the no-go decision in
[#74](https://github.com/acgetchell/dotfiles/issues/74) and skill removal in
[#118](https://github.com/acgetchell/dotfiles/pull/118).

## Fresh macOS setup

```sh
mkdir -p ~/projects
git clone https://github.com/acgetchell/dotfiles.git ~/projects/dotfiles
~/projects/dotfiles/bin/bootstrap.sh
```

`bootstrap.sh`:

1. installs Homebrew if missing;
2. runs `brew bundle install --file=Brewfile`;
3. installs Oh My Zsh if missing, preserving existing shell configuration;
4. stows `git`, `zsh`, and `agents`;
5. installs pinned Cargo tools: `cargo-update`, `dprint`, `just`, and `rumdl`;
6. runs `bin/verify.sh`.

After bootstrap, the equivalent discoverable setup entry point is:

```sh
cd ~/projects/dotfiles
just setup
```

`just setup` runs `bin/bootstrap.sh` with `DOTFILES_DIR` pointed at the current checkout, then syncs the uv-managed developer tools.

The repository's exact host-tool pins for `cargo-update`, `dprint`, `just`, and `rumdl`
live in `justfile`; `pyproject.toml` owns the exact uv pin and the locked Python tools,
including zizmor. Bootstrap and CI use
`bin/resolve-just-version.sh` only for the pre-`just` bootstrap step; after
`just` is available, consumers resolve pins with
`just --evaluate <tool>_version` (use `cargo_update_version` for `cargo-update`).

## Linux review setup

From a checkout on a connected, site-approved Linux provisioning host:

```sh
bash bin/linux-review.sh setup
bash bin/linux-review.sh check
bash bin/linux-review.sh smoke
```

Setup reuses matching site tools or installs checksum-verified, pinned release
binaries and locked Python dependencies under `~/.local/share/dotfiles-review`.
It requires the base tools documented in the guide and can be rerun. It does
not require root, Homebrew, Docker, or system Python changes.
After setup, `just linux-setup`, `just linux-check`, and `just linux-smoke`
expose the same commands when the pinned Just is on PATH.
`bin/linux-review.sh exec just --list` uses the provisioned PATH without changing
shell startup files. The retained `just linux-probe` is only for a separately
authorized optional TypeSafe evaluation; it is not part of environment acceptance.

## Day-to-day stow commands

Supported stow packages are `git`, `zsh`, and `agents`.

```sh
# Preview changes before applying a package.
just stow-check agents

# Apply one package and print the symlink operations performed.
just stow-apply zsh

# Apply all managed packages and print their symlink operations.
just stow-apply-all

# Restow one package, refreshing existing links with explicit unlink/link output.
just stow-restow agents

# Restow all managed packages.
just stow-restow-all

# Remove one package's symlinks and print the removals.
just stow-delete zsh

# Adopt an existing live file into the repo (overwrites the package copy).
just stow-adopt zsh

# Verify stowed links resolve into this repo; flag dangling or missing links.
just stow-verify
```

Use `--adopt` only when intentionally moving an existing `$HOME` file into dotfiles. Always inspect the resulting package file changes before committing.

The `just` stow recipes always pass `-d "$PWD"` and `-t "$HOME"`.
The `git` and `zsh` packages also use `--no-folding`. The `agents` package
allows directory folding because Codex discovers symlinked skill folders but
skips individual `SKILL.md` symlinks. Run `just stow-restow agents` to migrate
an older installation that used file-level links. `just stow-verify` flags
that incompatible layout. If running raw `stow`, use the same package-specific
options and explicit source and target directories.

For new package-owned files such as Codex skills, create the file under the package, run `just stow-check <package>`, then run `just stow-apply <package>` when the dry run looks right. `stow-check` is the only simulation-mode recipe; `stow-apply` and `stow-apply-all` stow missing or new links, while `stow-restow` and `stow-restow-all` perform full unlink/link refreshes. Mutating recipes print the Stow link operations they perform. `just stow-all` remains as an alias for `just stow-apply-all`. Stow recipes do not stage, commit, or print source-control status.

After applying or restowing packages, `just stow-verify` (backed by `scripts/stow_verify.py`) confirms every stowed link resolves to its expected file inside this repo and flags dangling links left behind by renamed or removed packages or skills. After `stow-delete`, missing-link failures are expected until the package is reapplied. `bin/verify.sh` runs the same check.

## Brewfile workflow

`Brewfile` is intentionally foundational: core CLI tools, developer casks, and apps expected on every machine.
On macOS, Homebrew owns `pkgx`, `rustup`, and the `pyproject.toml`-pinned `uv`; Cargo owns the
`justfile`-pinned, directly invokable `dprint`, `just`, and `rumdl` binaries,
plus `cargo-update`, which provides `cargo-install-update`. Zizmor belongs to
the repository's locked Python environment.
Repository-scoped build tools, formatters, linters, and occasional maintenance
tools should be supplied ephemerally through pkgx or the repository's
language-specific environment rather than added here.

```sh
# Install missing formulae/casks
just brew-install

# Verify every Brewfile dependency is installed
just brew-check

# Preview formulae and casks not owned by the Brewfile
just brew-cleanup-preview

# Uninstall the previewed formulae/casks and perform Homebrew cache cleanup
just brew-cleanup

# Upgrade the Brewfile, Python pins/environment, and all installed Cargo tools
just update

# Snapshot the current machine for review, without committing it
brew bundle dump --file=~/projects/dotfiles/Brewfile.local --force --describe
```

`Brewfile.local` is gitignored. Use it to audit one-off apps before deciding whether they belong in the committed foundational `Brewfile`.
`just brew-cleanup-preview` never passes Homebrew's destructive `--force` flag. Homebrew returns status 1 when the preview finds cleanup candidates; the recipe treats that documented result as a successful preview while preserving actual errors. `just brew-cleanup` asks for confirmation before passing `--force` and applying that cleanup.

`just update` upgrades the Brewfile dependencies, advances exact direct Python development-tool
pins in `pyproject.toml`, and refreshes the complete `uv.lock` and development environment.
`just update-python-dependencies` runs the Python portion independently.
The locked `research-repo-tools` package supplies pin updates, uv preflight, and tool-pin
reconciliation. Its exact pin lives in the included `tooling` group and changes only through
an explicit package upgrade; ranges, markers, and other included-group constraints remain intact.
It also runs `cargo install-update -a --locked`, updating all Cargo-installed tools with
their published lockfiles, including tools such as `cargo-nextest` that require `--locked`.
The `cup` shell alias runs the same Cargo command; `just update-cargo-tools` additionally
reconciles the repository-owned `justfile` pins (`cargo-update`, `dprint`, `just`, and `rumdl`).
The Cargo tool update requires
`cargo-install-update` from the `cargo-update` package, installed by bootstrap and checked by `bin/verify.sh`.
The owned pin mapping lives in `[tool.research-repo-tools.deps.tools]` in `pyproject.toml`.
Cargo pins use the shared package's SemVer contract, including prerelease/build suffixes;
the bootstrap and version checks preserve those suffixes. The exact uv pin lives only in
`[tool.uv].required-version`; Just and CI read it. `just update-uv` uses the shared
updater to upgrade uv through Homebrew and reconcile that declaration.
The shared launcher selects Homebrew uv before resolving or updating pins. Bootstrap remains
self-contained shell code; `just setup` installs the locked Python environment and
the repository's managed security scanners afterward.
Updates stop on failure, but successful package-manager steps remain applied; rerun after
resolving the failure to finish synchronization and pin reconciliation.

The same locked package owns the Semgrep fixture runner and CodeRabbit wrapper.
`just semgrep-test` reads `[tool.research-repo-tools.semgrep]`; the repository keeps its
rules and real fixtures while generic runner tests live upstream.
The Jupyter review skill delegates notebook inspection, advice, validation, native
Ruff/ty lint, cleanup, and execution to published v0.1.8 shared commands. It keeps
only review policy and a tested consumer configuration template; generic notebook
implementation and regression coverage live upstream. See the
[shared notebook workflow](agents/.agents/skills/jupyter-notebook-review/references/shared-notebooks.md)
for locked-consumer and isolated inspection commands. Dotfiles' development
environment includes `nbformat` for read-only consumer integration tests; notebook
execution dependencies belong to each consumer's locked notebook environment.

### Shared tooling and Python upgrades

Dotfiles adopts `research-repo-tools==0.1.8` for Python baseline inheritance,
tracked and nonignored file selection, notebook policy, workflow audits, dependency
and secret scans, and managed scanner setup/cleanup. The
[adoption map](docs/shared-tooling.md) records the command owners and scope.

`just workflow-allowlist-check` delegates action-step and reusable-workflow checks
to the installed shared package, using `.github/settings/actions-selected.json`
as the sole allowlist. It remains part of `github-actions-check` and CI; actionlint
owns workflow syntax and zizmor owns SHA pinning. The reusable Dependabot approval
workflow retains its separately reviewed commit pin.

When a published shared-tools release adopts Python 3.15, migrate with its version:

```sh
just shared-python-plan VERSION
just shared-python-update VERSION
just ci
just security
```

The shared package updates the Python selector, dependency-only runtime requirement,
package pin, lockfile, and environment together. CI checks these mirrors against the
installed package. Ruff and ty infer the target; workflows read `.python-version`.
A new upstream release takes effect here through this explicit pinned migration.
Homebrew's unversioned `python` formula serves the host; uv selects repository Python.

`just tools-sync` installs checksum-verified OSV/Gitleaks into the package-owned
`~/.cache/research-repo-tools` store; `just tools-check` verifies them. `just security`
scans the real `uv.lock`, full reachable Git history, and current files, writing redacted
reports under `target/security`. It requires online advisory access and runs in the
required CI `verify` job. `just security-check` remains an alias. Run
`just security-osv` or `just security-secrets` for either scan separately;
`just update-security-tools` updates their managed pins and installations.
`just clean` previews obsolete managed installations;
`just clean --apply` removes eligible package-owned candidates after checking again.
Pass `--keep-root PATH` for other consumers that share this store.

`just zizmor` is an explicit offline audit. `just zizmor-check --require-online`
runs the same locked scanner/persona with authenticated online audits; the dedicated
workflow also publishes SARIF when authorized. Zizmor now comes from the locked Python
environment. Existing user-wide Cargo installations are outside repository setup.

`bin/verify.sh` derives its cask and CLI checks from the Brewfile, so removing an entry there never causes a stale verify failure. It also surfaces `brew missing` output as warnings; some casks (e.g. `mactex`) declare Homebrew dependencies they actually bundle themselves, so those lines are informational rather than fatal.

## macOS defaults

`bin/macos-defaults.sh` captures this machine's explicitly set system preferences (auto light/dark appearance, Dock, Finder, keyboard text input, trackpad) as idempotent `defaults write` commands.

```sh
just macos-defaults
```

The recipe asks for confirmation, then restarts Dock and Finder; appearance changes may need a logout/login. It is intentionally not part of `bootstrap.sh` — run it once per machine when the captured preferences are wanted.

The default recipe leaves native macOS WindowManager tiling unchanged. To let
an installed Rectangle Pro take over drag-to-edge tiling, run
`just macos-defaults-rectangle-pro` and accept its separate confirmation. The
takeover is skipped, without changing native tiling, when the Rectangle Pro
cask is unavailable.

## Sanity checks

Run the main check:

```sh
cd ~/projects/dotfiles
just ci
```

Apply the repository's safe mechanical fixers with `just fix`. Use
`just justfile-fmt`, `just markdown-fix`, or `just python-fix` to run one fixer
directly. Run `just markdown-check` for Markdown validation without mutation.

Manual checks that should pass:

```sh
# bootstrap health check
~/projects/dotfiles/bin/verify.sh

# stow symlinks resolve into this repo; dangling links are flagged
just stow-verify

# inspect individual links manually if needed
ls -la ~/.zshrc ~/.gitconfig
readlink ~/.zshrc
readlink ~/.gitconfig

# global skills are available from ~/.agents/skills
ls ~/.agents/skills/*/SKILL.md

# git reads public config plus local include
git config --global --get user.email
git config --global --includes --get coderabbit.machineId

# brew is healthy
just brew-check
brew doctor

# shell config parses
zsh -n ~/.zshrc
```

Expected symlink shape:

```text
~/.zshrc                  -> projects/dotfiles/zsh/.zshrc
~/.gitconfig              -> projects/dotfiles/git/.gitconfig
~/.agents/skills/*        -> ../../projects/dotfiles/agents/.agents/skills/*
```

## CodeRabbit review

Install and authenticate the CodeRabbit CLI separately, then run:

```sh
# Review committed branch changes and local edits against verified origin/main.
just review

# Explicitly use a local comparison base instead.
just review main

# Review only staged, unstaged, and non-ignored untracked files.
just review-uncommitted
```

Both recipes emit structured findings and pass `AGENTS.md` and `.coderabbit.yaml`
as review instructions. The default `origin/main` must match the remote branch;
refresh a stale remote-tracking reference before retrying. An explicit
`just review <base>` uses a locally available commit or reference without that
remote freshness check. CodeRabbit reviews are opt-in and separate from `just ci`.

## Dependabot approvals

Dependabot uses the shared approval workflow with exact ecosystem/file policy.
See the [rollout and hosted verification procedure](.github/DEPENDABOT.md) for
required GitHub settings, current-head approvals, and post-merge CI dispatch.

## Shared agent skills

Keep reusable skills in `agents/.agents/skills/<skill-name>/`. Stow exposes
them at `~/.agents/skills/`, which Codex discovers across repositories,
including symlinked skill directories. See the
[Codex skill documentation](https://developers.openai.com/codex/skills).
Other agents can use the same `SKILL.md` format; discovery locations vary by
agent, so configure or link its skill directory to the shared skill folder.

### Optional TypeSafe evaluation

The completed [routing evaluations](docs/typesafe-threshold-evaluation.md) did
not justify adoption. [#74](https://github.com/acgetchell/dotfiles/issues/74) is
closed as not planned; [#75](https://github.com/acgetchell/dotfiles/issues/75)
tracks a future evaluation of a pinned model or question revision. Ordinary
coordinator routing and evidence acceptance remain authoritative.

The opt-in shadow harness, fixtures, offline replay, budget controls, and
evaluation records are retained. Run `just review-routing-experiment` to prepare
the fixtures offline; see the [experiment guide](agents/.agents/skills/review-graph/references/routing-experiment.md)
for replay and explicitly authorized live evaluations. The existing cases are
historical regression and development data; future adoption decisions require
fresh held-out cases and a prospectively frozen success rule.

The upstream TypeSafe agent skill is no longer vendored. API use requires a
separately configured `TYPESAFE_API_KEY`; keep credentials out of this public
repository.

After updating a directory-link installation, run `just stow-restow agents`
followed by `just stow-verify`. For an older file-level installation where
`~/.agents/skills/typesafe-ai` is a real directory, inspect it first. Unlink only
dangling symlinks whose resolved targets lie inside this checkout's removed
`agents/.agents/skills/typesafe-ai/` tree, preserving real files and links to
other installations. Remove only directories that become empty, then run the
same restow and verification commands.

Store the API key in a 1Password item. Enable the desktop app's CLI integration,
then use a secret reference to inject the key for one command:

```sh
just typesafe-local 'op://<vault>/<item>/<field>' just typesafe-check
```

Replace the reference with your item's **Copy Secret Reference** value. If you
use multiple 1Password accounts, prefix the command with
`OP_ACCOUNT='<account sign-in address or ID>'`. The command may prompt for
1Password authorization. The reference is configuration; never pass the actual
key as a command argument or commit it in a file. No shell startup-file changes
are required. `typesafe-local` can wrap other TypeSafe commands the same way.

`just typesafe-check` reads the injected `TYPESAFE_API_KEY`, calls the TypeSafe
model-list endpoint, and reports only authentication status and model count.
It makes no inference request and sends no repository content. It does not log
the key or raw response/error bodies. Keep 1Password's output masking enabled.
When a cloud environment supplies `TYPESAFE_API_KEY` through its secret provider,
run `just typesafe-check` directly. Credential provisioning is separate for each
execution environment.

For the configured Codex Cloud coding environment:

1. Allow HTTPS access to `api.typesafe.ai` and have the environment request a
   personal **Network secret** named `TYPESAFE_API_KEY` for that destination.
2. In **Settings > Codex Cloud > Personal vault**, add a **Network secret** with
   the matching key, enter the API key through the private settings form, and
   apply it to the coding environment. Personal secrets do not automatically
   add network destinations to the environment's allowlist.
3. Save and publish the environment configuration. Once these repository changes
   are available in its checkout, run `just typesafe-check` in a new cloud task.

The cloud process receives a placeholder; its HTTPS proxy supplies the real
credential for the allowed destination. The local 1Password session is not
needed for cloud runs. See the official
[cloud environment secret configuration](https://learn.chatgpt.com/docs/environments/cloud-environments#configure-environment-variables-and-network-secrets).

## Global agent instructions

The `agents` package keeps shared defaults in `agents/.agents/AGENTS.md`,
installed as `~/.agents/AGENTS.md` for
[Warp](https://github.com/warpdotdev/warp/pull/9325).
[Codex](https://learn.chatgpt.com/docs/agent-configuration/agents-md) uses the same
file through a local `~/.codex/AGENTS.md` symlink. These defaults apply across
repositories; each repository can supply more specific instructions.

Branch creation follows the repository's documented or established convention,
with `<type>/<short-kebab-description>` as the fallback. Agent or model prefixes
such as `codex/` require an explicit request. Choose the final name before the
first push or pull request.

Install with `just stow-check agents`, then `just stow-apply agents` and
`just stow-verify`. Connect Codex once per host:

```sh
mkdir -p ~/.codex
ln -s ../.agents/AGENTS.md ~/.codex/AGENTS.md
```

If either instruction path already contains a regular file, review and preserve
its contents before moving it aside. Stow and `ln -s` report conflicts rather
than overwriting files. Keep `~/.codex` itself as a local directory; only the
instruction file links to the shared source. Start a new Codex session to load
the instructions. A nonempty `~/.codex/AGENTS.override.md` takes precedence;
a custom `CODEX_HOME` needs the link there instead. Remote and cloud agents need
the same setup on their own execution host.

## Codex config

Codex rewrites `~/.codex/config.toml` with app runtime state, local absolute
paths, project trust entries, plugin metadata, and other machine-specific
values. Keep that file local rather than stowing it from this public repo.

Useful non-secret defaults to keep in the local file include the sandbox mode, a
narrow uv cache exception, and sandboxed local network access for tools such as
Jupyter kernels:

```toml
[sandbox_workspace_write]
network_access = true
writable_roots = ["/Users/<username>/.cache/codex/uv"]

[shell_environment_policy]
set = { UV_CACHE_DIR = "/Users/<username>/.cache/codex/uv" }
```

This lets Rust/Python workflows use `uv run`, `uv lock`, and notebook execution
without giving Codex write access to all of `~/.cache` or disabling sandboxing.
The network exception is intentionally attached to `workspace-write`; it is
needed for local kernel sockets such as Jupyter's loopback ports.
Replace `/Users/<username>` with the absolute home path on the local machine;
keep the resulting machine-specific `~/.codex/config.toml` out of this repo.

Keep secrets and mutable runtime state out of this public repo. Do not commit
`~/.codex/auth.json`, logs, caches, sqlite state, marketplace cache state,
connector tokens, machine-local project trust entries, or opaque app-generated
identifiers.

## Local override files

Local override files are not tracked and should not be committed.

### `~/.zshrc.local`

Use for machine-specific shell paths, aliases, and experiments. It is sourced last by `zsh/.zshrc`.
Keep host-specific SSH aliases and work/institution endpoints here rather than
in the tracked `zsh/.zshrc`.

Example:

```sh
export SOME_LOCAL_PROJECT="$HOME/projects/private-tool"
alias work-vpn="tailscale up --accept-routes"
```

### `~/.gitconfig.local`

Use for per-machine git config such as tool machine IDs, signing keys, or work-specific identity.

The tracked `git/.gitconfig` includes it via:

```ini
[include]
	path = ~/.gitconfig.local
```

Example:

```ini
[coderabbit]
	machineId = cli/example
[user]
	signingkey = YOUR_SIGNING_KEY_ID
```

When checking included values with `git config`, pass `--includes`:

```sh
git config --global --includes --get coderabbit.machineId
```

### `Brewfile.local`

Use for a temporary `brew bundle dump` snapshot of the current machine. It is for review only; copy intentional entries into `Brewfile`.

## Skills

Codex and Warp/Oz both load skills from `~/.agents/skills/`, so the `agents` stow package provides one global source of truth across languages, activities, and repositories.

Following the [Astra skill guidance](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra),
keep discovery descriptions short and select by language or activity. Repository
references provide conditional context; they are not invocation gates. Preserve
automatic discovery, load only relevant modes and references, and keep scientific
oracles, human authorship, source identity, and immutable evidence requirements
explicit. Existing authorization remains valid for the same action and scope.
Reviews alone do not authorize upgrades or publication. Focused regression checks
may precede a required final gate; disclose overlap without double-counting it.

Review-graph path matches nominate specialists. The coordinator must assess each
matched candidate semantically, including justified non-applicability; the planner
rejects missing decisions. Mandatory coverage and proof gates remain authoritative.

To add a skill:

1. create `agents/.agents/skills/<skill-id>/SKILL.md`;
2. add YAML frontmatter with `name` and a triggering `description`;
3. add `agents/.agents/skills/<skill-id>/agents/openai.yaml` with a required
   `interface` mapping containing `display_name`, a 25–64 character
   `short_description`, and a `default_prompt` that explicitly mentions
   `$skill-id`;
4. validate and re-stow the package:

```sh
just skill-check agents/.agents/skills/<skill-id>
just stow-check agents
just stow-apply agents
```

Run `just check-skills` to validate tracked and nonignored skills in one Python
process, with per-skill diagnostics and an aggregate exit status. Removed
entrypoints are omitted; explicitly checking a missing skill still fails.

`just test-review-contracts` runs cheap prompt-budget and routing guards.
`just test-python` runs that gate followed by the remaining tests, and `just ci`
runs it before static checks and graph execution. Each guard runs once in either
aggregate. Direct `uv run --locked pytest` still collects the complete suite.

Review the changed skill files separately before including them in a commit.

Recommended frontmatter style:

```yaml
---
name: rust-example
description: "Review Rust generic constraints when bound necessity or downstream usability is in question."
---
```

## Public repo safety policy

Commit:

- shell aliases, functions, and portable PATH setup;
- Git defaults and non-secret identity;
- public SSH host aliases;
- VS Code settings and extension lists;
- template `.env.example` files with placeholder values;
- skill instructions.

Do not commit:

- private SSH keys;
- API keys, tokens, passwords, or recovery codes;
- real `.env` files;
- tenant-specific credentials or service principal secrets;
- downloaded certificates or key material;
- per-machine app IDs or opaque tool identifiers.

Use 1Password for secrets and local ignored files for machine-specific configuration.
