# My Dotfiles

Personal macOS dotfiles managed with [GNU Stow](https://www.gnu.org/software/stow/)
and [Homebrew Bundle](https://docs.brew.sh/Brew-Bundle-and-Brewfile), plus
user-space development and review tooling for Linux, cloud, and HPC hosts.
This public repo contains reproducible, non-secret defaults.

## Contents

- [Setup](#setup)
  - [Platform scope](#platform-scope)
  - [Fresh macOS setup](#fresh-macos-setup)
  - [Linux review setup](#linux-review-setup)
  - [Verify a setup](#verify-a-setup)
- [Development workflow](#development-workflow)
- [Maintain dotfiles](#maintain-dotfiles)
  - [Stow and local overrides](#stow-and-local-overrides)
  - [Homebrew and tooling updates](#homebrew-and-tooling-updates)
- [Agent skills and instructions](#agent-skills-and-instructions)
  - [Shared agent skills](#shared-agent-skills)
  - [Global agent instructions](#global-agent-instructions)
- [Layout](#layout)

## Setup

### Platform scope

| Environment | Setup and checks |
| --- | --- |
| macOS | Desktop dotfiles, Homebrew, Stow, and full repository checks. See [macOS setup](#fresh-macos-setup). |
| Ubuntu 24.04 or Debian 13 (x86_64) | The `linux-cloud` rebuild profile adds shell and Git config, skills, and offline restoration. See [rebuild profiles](docs/rebuild-profiles.md). |
| Site-managed Linux, cloud, and HPC | The tooling-only installer accepts x86_64 or aarch64 with glibc 2.34 or newer. See the [Linux guide](docs/linux-review-environment.md) for prerequisites and native evidence. |
| Windows | CI covers the timing helper and a locked Semgrep engine smoke test. See the [native CI record](docs/validation-adoption.md#native-ci-measurements). |

### Fresh macOS setup

```sh
mkdir -p ~/projects
git clone https://github.com/acgetchell/dotfiles.git ~/projects/dotfiles
cd ~/projects/dotfiles
bash bin/bootstrap.sh
```

Bootstrap installs Homebrew dependencies and Oh My Zsh, links the `git`, `zsh`,
and `agents` packages, installs pinned Cargo tools, and verifies the setup.
Resolve any Stow conflicts before retrying.

Once Homebrew and Just are on `PATH`, run `just python-sync` and
`just tools-sync` to install the locked Python environment and managed security
scanners. With Just already installed, `just setup macos` runs the full setup.

Run `just macos-defaults` separately to apply the captured Dock, Finder, input,
and appearance preferences. It prompts before applying changes and restarts Dock
and Finder. Use `just macos-defaults-rectangle-pro` if you also want Rectangle
Pro to handle drag-to-edge tiling.

### Linux review setup

On a site-approved host with the
[base tools](docs/linux-review-environment.md#supported-candidates-and-base-tools)
installed, run from the checkout:

```sh
bash bin/linux-review.sh setup
bash bin/linux-review.sh check
bash bin/linux-review.sh smoke
```

Setup installs pinned tools in user-owned directories. The check and scripted
smoke run offline after provisioning. Use
`bash bin/linux-review.sh exec just --list` to use the provisioned tools.
For shell and Git setup on Ubuntu or Debian, follow the
[Linux rebuild profile](docs/rebuild-profiles.md#platform-setup). Use the
[cloud provisioning and restoration guide](docs/rebuild-profiles.md#connected-provisioning-and-offline-restoration)
to prepare or recover locked repository environments.

### Verify a setup

After setup, open a fresh shell and run the check for your installation.

| Setup | Command | What it checks |
| --- | --- | --- |
| macOS | `just profile-doctor macos` | Homebrew dependencies, pinned tools, and Stow links through `bin/verify.sh`. |
| Linux rebuild profile | `just profile-doctor linux-cloud` | Pinned tools, fresh Bash and Zsh sessions, links, and the installed skill helper. |
| Tooling-only Linux | `bash bin/linux-review.sh check` | The provisioned environment and the offline portable CI suite. |

## Development workflow

Run these commands from the checkout. Run both pre-push checks on the final
changes, then complete the local review for a PR push.

| When | Command | Purpose |
| --- | --- | --- |
| During iteration | `just check` | Run static checks and early review guards. |
| Before pushing | `just security` | Check the lockfile for known vulnerabilities and scan Git history and current files for secrets. |
| Before pushing | `just ci` | Run the iteration checks, the Semgrep scan and fixtures, and the remaining Python tests. |
| Before a PR push | `just review` | Review outgoing changes and local edits with CodeRabbit. |

The Brewfile installs the [CodeRabbit CLI](https://docs.coderabbit.ai/cli) on
macOS. Install it separately on Linux and authenticate before running
`just review`. The default comparison base is verified `origin/main`. Follow
the [PR push and paid-review policy](agents/.agents/AGENTS.md#required-pr-push-gates).

Run `just --list` to see all recipes.

See the guides for [CI evidence](docs/validation-adoption.md),
[review validation handoffs](docs/review-validation-system.md), and
[Dependabot approvals](.github/DEPENDABOT.md).

## Maintain dotfiles

### Stow and local overrides

On macOS, Stow links [`git/`](git/), [`zsh/`](zsh/), and [`agents/`](agents/)
into your home directory. Run these recipes from the checkout.

| Task | Command |
| --- | --- |
| Preview, then link a package | `just stow-check zsh`, then `just stow-apply zsh` |
| Link all packages | `just stow-apply-all` |
| Refresh links | `just stow-restow agents` or `just stow-restow-all` |
| Remove a package's links | `just stow-delete zsh` |
| Check for missing or dangling links | `just stow-verify` |

`just stow-adopt PACKAGE` moves existing home files into the checkout and can
overwrite the package copies. Inspect the resulting diff before committing.

Keep machine-specific shell settings in `~/.zshrc.local` and Git identity,
signing settings, or tool IDs in `~/.gitconfig.local`. The tracked configs load
both files. Keep credentials in 1Password or the host's secret store, and keep
`~/.codex/config.toml` and other app state local.

### Homebrew and tooling updates

[`Brewfile`](Brewfile) lists the tools and apps expected on every Mac. Use
`just brew-install` to install missing entries and `just brew-check` to verify
them. Preview removals with `just brew-cleanup-preview` before running
`just brew-cleanup`, which prompts before uninstalling formulae and casks.
Use `brew bundle dump --file=Brewfile.local --force --describe` for an ignored
snapshot to review.

`just update macos` updates Homebrew, uv, the Python environment, Cargo tools,
and managed security scanners. `just update linux-cloud` restores the
checked-in versions. See [tooling upgrades](docs/shared-tooling.md#python-authority-and-upgrades)
for dependency updates and Python migrations.

[research-repo-tools](https://pypi.org/project/research-repo-tools/) supplies the
Python baseline, dependency updates, file selection, workflow and security
checks, notebook commands, and the CodeRabbit wrapper. The
[shared tooling guide](docs/shared-tooling.md) maps those capabilities to this
repo's recipes. Source and upstream documentation are on
[GitHub](https://github.com/acgetchell/research-repo-tools).

## Agent skills and instructions

### Shared agent skills

Skills live in [`agents/.agents/skills/`](agents/.agents/skills/) and are linked
as directories under `~/.agents/skills/`. Use `just stow-restow agents` to
refresh an older file-level layout, or follow the
[skills-only setup](docs/rebuild-profiles.md#skills-without-desktop-setup).

To add a skill, create its `SKILL.md` with `name` and `description` frontmatter.
Add `agents/openai.yaml` in the skill directory with its display name, short
description, and a default prompt that mentions the skill. Then validate and
link it.

```sh
just skill-check agents/.agents/skills/SKILL-ID
just stow-check agents
just stow-apply agents
just stow-verify
```

Run `just check-skills` to validate the full skill inventory. The
[TypeSafe routing experiment guide](agents/.agents/skills/review-graph/references/routing-experiment.md)
covers the optional evaluation and its historical results.

### Global agent instructions

The `agents` package also links
[shared agent instructions](agents/.agents/AGENTS.md) to `~/.agents/AGENTS.md`.
To use them in Codex, create a link from your Codex home.

```sh
mkdir -p "${CODEX_HOME:-$HOME/.codex}"
ln -s "$HOME/.agents/AGENTS.md" "${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
```

Preserve any existing instructions before replacing a file or link. Start a new
Codex session to load the instructions.

## Layout

The `git/`, `zsh/`, `bash/`, and `agents/` packages mirror paths under `$HOME`.

```text
dotfiles/
├── Brewfile                # macOS formulae and casks
├── justfile                # setup, maintenance, and validation recipes
├── pyproject.toml          # uv-managed Python tooling
├── semgrep.yaml            # repository-owned guardrail rules
├── bin/
│   ├── bootstrap.sh        # fresh macOS setup
│   ├── linux-review.sh     # site-managed Linux review tooling
│   ├── setup-profile.sh    # macOS and Linux rebuild profiles
│   ├── macos-defaults.sh   # optional macOS preferences
│   └── verify.sh           # macOS health check
├── docs/                   # setup guides and validation evidence
├── profiles/
│   └── cloud.toml          # cloud provisioning inventory
├── scripts/
│   ├── skill_validate.py   # agent skill metadata checks
│   └── stow_verify.py      # Stow symlink integrity check
├── tests/
│   └── semgrep/            # Semgrep rule fixtures
├── bash/
│   ├── .bash_profile       # Bash startup on linux-cloud
│   └── .bashrc
├── git/
│   └── .gitconfig          # links to ~/.gitconfig
├── zsh/
│   └── .zshrc              # links to ~/.zshrc
└── agents/
    └── .agents/
        ├── AGENTS.md       # linked by macOS setup
        └── skills/         # shared agent skills
            └── */SKILL.md
```
