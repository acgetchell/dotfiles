#!/usr/bin/env bash
# Migrate legacy skill file links without deleting user-authored files.
set -euo pipefail

DOTFILES_DIR="${1:?dotfiles directory required}"
DOTFILES_DIR="$(cd "$DOTFILES_DIR" && pwd -P)"
restore_links() {
  status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    echo "==> Restoring managed skill links after failed migration" >&2
    if ! stow -d "$DOTFILES_DIR" -t "$HOME" -S agents; then
      echo "==> Could not restore all links; resolve Stow conflicts and rerun just stow-apply agents." >&2
    fi
  fi
  exit "$status"
}
stow -d "$DOTFILES_DIR" -t "$HOME" -D agents
trap restore_links EXIT
for source in "$DOTFILES_DIR/agents/.agents/skills/"*; do
  target="$HOME/.agents/skills/${source##*/}"
  if [[ -d "$source" && -d "$target" && ! -L "$target" ]]; then
    # Unlink only bytecode symlinks resolving inside this repository.
    while IFS= read -r -d '' artifact; do
      if resolved="$(realpath "$artifact" 2>/dev/null)"; then
        case "$resolved" in
        "$DOTFILES_DIR"/*) rm "$artifact" ;;
        esac
      fi
    done < <(find "$target" -type l \( -name '*.pyc' -o -name '*.pyo' \) -print0)
    # Do not follow symlinks or remove unknown files, even inside __pycache__.
    find "$target" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
    find "$target" -depth -type d -empty -delete
    if [[ -e "$target" ]]; then
      echo "==> Skill migration blocked by remaining files in $target" >&2
      echo "    Move these files aside after manual review, then rerun bootstrap or just stow-restow agents." >&2
      exit 1
    fi
  fi
done
stow -d "$DOTFILES_DIR" -t "$HOME" -S agents
for source in "$DOTFILES_DIR/agents/.agents/skills/"*; do
  [[ -f "$source/SKILL.md" ]] || continue
  manifest="$HOME/.agents/skills/${source##*/}/SKILL.md"
  if [[ ! -f "$manifest" || -L "$manifest" ]]; then
    echo "==> Skill migration failed: $manifest must be a regular file through a directory symlink." >&2
    exit 1
  fi
done
trap - EXIT
