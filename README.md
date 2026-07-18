# My Dotfiles
Personal macOS dotfiles managed with [GNU Stow](https://www.gnu.org/software/stow/) and [Homebrew Bundle](https://github.com/Homebrew/homebrew-bundle).

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
│   └── verify.sh           # health check / sanity check
├── scripts/
│   └── semgrep_fixture_config.py
├── tests/
│   └── semgrep/            # Semgrep rule fixtures
├── git/
│   └── .gitconfig          # stows to ~/.gitconfig
├── zsh/
│   └── .zshrc              # stows to ~/.zshrc
└── agents/
    └── .agents/skills/     # stows to ~/.agents/skills/
        └── */SKILL.md
```

## Fresh-machine setup

```sh
mkdir -p ~/projects
git clone https://github.com/acgetchell/dotfiles.git ~/projects/dotfiles
~/projects/dotfiles/bin/bootstrap.sh
```

`bootstrap.sh`:

1. installs Homebrew if missing;
2. runs `brew bundle install --file=Brewfile`;
3. stows `git`, `zsh`, and `agents`;
4. installs pinned cargo tools such as `just` and `zizmor`;
5. runs `bin/verify.sh`.

After bootstrap, the equivalent discoverable setup entry point is:

```sh
cd ~/projects/dotfiles
just setup
```

`just setup` runs `bin/bootstrap.sh` with `DOTFILES_DIR` pointed at the current checkout, then syncs the uv-managed developer tools.

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
```

Use `--adopt` only when intentionally moving an existing `$HOME` file into dotfiles. Always inspect the resulting package file changes before committing.

The `just` stow recipes always pass both `-d "$PWD"` and `-t "$HOME"`. If running raw `stow`, pass both paths explicitly; otherwise stow targets the parent of the current directory, which can create links in the wrong place.

For new package-owned files such as Codex skills, create the file under the package, run `just stow-check <package>`, then run `just stow-apply <package>` when the dry run looks right. `stow-check` is the only simulation-mode recipe; `stow-apply` and `stow-apply-all` stow missing or new links, while `stow-restow` and `stow-restow-all` perform full unlink/link refreshes. Mutating recipes print the Stow link operations they perform. `just stow-all` remains as an alias for `just stow-apply-all`. Stow recipes do not stage, commit, or print source-control status.

## Brewfile workflow
`Brewfile` is intentionally foundational: core CLI tools, developer casks, and apps expected on every machine.

```sh
# Install missing formulae/casks
brew bundle install --file=~/projects/dotfiles/Brewfile

# Verify every Brewfile dependency is installed
brew bundle check --file=~/projects/dotfiles/Brewfile

# Snapshot the current machine for review, without committing it
brew bundle dump --file=~/projects/dotfiles/Brewfile.local --force --describe
```

`Brewfile.local` is gitignored. Use it to audit one-off apps before deciding whether they belong in the committed foundational `Brewfile`.

## Sanity checks
Run the main check:

```sh
cd ~/projects/dotfiles
just ci
```

Apply the repository's safe mechanical fixers with `just fix`. Use
`just justfile-fmt` or `just python-fix` to run one fixer directly.

Manual checks that should pass:

```sh
# bootstrap health check
~/projects/dotfiles/bin/verify.sh

# stow symlinks point into this repo
ls -la ~/.zshrc ~/.gitconfig
readlink ~/.zshrc
readlink ~/.gitconfig

# global skills are available from ~/.agents/skills
ls ~/.agents/skills/*/SKILL.md

# git reads public config plus local include
git config --global --get user.email
git config --global --includes --get coderabbit.machineId

# brew is healthy
brew bundle check --file=~/projects/dotfiles/Brewfile
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
Codex and Warp/Oz both load skills from `~/.agents/skills/`, so the `agents` stow package provides one global source of truth across Rust repos.

To add a skill:

1. create `agents/.agents/skills/<skill-id>/SKILL.md`;
2. add YAML frontmatter with `name` and a triggering `description`;
3. add `agents/.agents/skills/<skill-id>/agents/openai.yaml` with
   `display_name`, a 25–64 character `short_description`, and a
   `default_prompt` that explicitly mentions `$skill-id`;
4. validate and re-stow the package:

```sh
just skill-check agents/.agents/skills/<skill-id>
just stow-check agents
just stow-apply agents
```

Run `just check-skills` to validate every skill in `agents/.agents/skills/`.

Review the changed skill files separately before including them in a commit.

Recommended frontmatter style:

```yaml
---
name: rust-example
description: "Short trigger description. USE FOR: specific situations. DO NOT USE FOR: exclusions."
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
