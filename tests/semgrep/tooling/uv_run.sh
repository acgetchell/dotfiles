#!/usr/bin/env bash

# ruleid: dotfiles.tooling.uv-run-locked
uv run pytest

# ok: dotfiles.tooling.uv-run-locked
uv run --locked pytest

# ruleid: dotfiles.tooling.uv-run-locked
UV_CACHE_DIR=.uv-cache uv run ruff check .

# ok: dotfiles.tooling.uv-run-locked
UV_CACHE_DIR=.uv-cache uv run --locked ruff check .
