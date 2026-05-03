# My Dotfiles
Personal macOS dotfiles managed with [GNU Stow](https://www.gnu.org/software/stow/) and [Homebrew Bundle](https://github.com/Homebrew/homebrew-bundle).

This repo is intended to remain public. Committed files define reproducible, non-secret defaults; machine-specific values live in local ignored files such as `~/.zshrc.local`, `~/.gitconfig.local`, and `Brewfile.local`.

## Layout
Each top-level directory is a stow package. Package contents mirror paths under `$HOME`.

```text
dotfiles/
├── Brewfile                # foundational formulae + casks
├── bin/
│   ├── bootstrap.sh        # fresh-machine provisioner
│   └── verify.sh           # health check / sanity check
├── git/
│   └── .gitconfig          # stows to ~/.gitconfig
├── zsh/
│   └── .zshrc              # stows to ~/.zshrc
└── agents/
    └── .agents/skills/     # stows to ~/.agents/skills/
        ├── rust-style-hygiene/SKILL.md
        └── rust-test-quality/SKILL.md
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
4. runs `bin/verify.sh`.

## Day-to-day stow commands

```sh
# Apply or re-apply one package
stow -d ~/projects/dotfiles -t ~ -R zsh

# Remove one package's symlinks
stow -d ~/projects/dotfiles -t ~ -D zsh

# Adopt an existing live file into the repo (overwrites the package copy)
stow -d ~/projects/dotfiles -t ~ --adopt zsh
```

Use `--adopt` only when intentionally moving an existing `$HOME` file into dotfiles. Always inspect the resulting diff before committing.

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
~/projects/dotfiles/bin/verify.sh
```

Manual checks that should pass:

```sh
# stow symlinks point into this repo
ls -la ~/.zshrc ~/.gitconfig
readlink ~/.zshrc
readlink ~/.gitconfig

# global skills are available from ~/.agents/skills
ls ~/.agents/skills/rust-style-hygiene/SKILL.md
ls ~/.agents/skills/rust-test-quality/SKILL.md

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
~/.agents/skills/rust-*   -> ../../projects/dotfiles/agents/.agents/skills/rust-*
```

## Local override files
Local override files are not tracked and should not be committed.

### `~/.zshrc.local`
Use for machine-specific shell paths, aliases, and experiments. It is sourced last by `zsh/.zshrc`.

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
	signingkey = ABCDEF123456
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
3. re-stow:

```sh
stow -d ~/projects/dotfiles -t ~ -R agents
```

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
