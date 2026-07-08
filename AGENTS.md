# Repository Agent Instructions

This repository is public dotfiles. Keep committed changes non-secret,
machine-portable, and scoped to reproducible defaults.

## Python And Skill Validation

- Prefer `uv run` over bare `python3` for Python tooling in this repository.
- Do not install packages into system or Homebrew Python just to run a repo
  check.
- For Codex skill validation, prefer the repository recipes:

```sh
just skill-check agents/.agents/skills/<skill-id>
just check-skills
```

- If `just` is unavailable, run the underlying validator directly:

```sh
uv run python scripts/skill_validate.py <skill-dir>
```

- Use `uv run --with <package> ...` for one-off Python helper dependencies that
  are not part of this repo's locked environment.
- If `uv` needs network access or cache writes outside the sandbox, request
  approval instead of falling back to global Python package installation.
- In tracked docs and instructions, prefer `$HOME`, `~`, or placeholders over
  committed absolute paths such as `/Users/<name>/...`.

## Dotfiles Workflow

- Use `just` recipes as the primary command surface when they exist.
- Do not mutate git state unless explicitly requested.
- Do not edit local-only files such as `~/.codex/config.toml`,
  `~/.zshrc.local`, `~/.gitconfig.local`, or `Brewfile.local` from this repo.
