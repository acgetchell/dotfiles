#!/usr/bin/env bash
# verify.sh - confirm Brewfile bundle, stow symlinks, and core tooling are present.
#
# Use bash explicitly; zsh's word-splitting rules differ and trip the
# heredoc-style command lists below.

set -euo pipefail

DOTFILES_DIR="${DOTFILES_DIR:-$HOME/projects/dotfiles}"

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAILED=1; }

FAILED=0

echo "==> Brewfile"
if brew bundle check --file="$DOTFILES_DIR/Brewfile" >/dev/null 2>&1; then
  pass "brew bundle check"
else
  brew bundle check --verbose --file="$DOTFILES_DIR/Brewfile" || true
  fail "brew bundle check (run: brew bundle install --file=$DOTFILES_DIR/Brewfile)"
fi

echo "==> CLI tools"
TOOLS=(
  actionlint ansible az cargo docker dotnet gh git helm
  just kubectl node op pwsh python3 rustc ssh stow tailscale
  zizmor
)
for tool in "${TOOLS[@]}"; do
  if command -v "$tool" >/dev/null 2>&1; then
    pass "$tool"
  else
    fail "$tool not on PATH"
  fi
done

echo "==> Casks"
CASKS=(
  1password 1password-cli gitkraken mactex notion
  obsidian slack visual-studio-code warp zed zotero
)
for c in "${CASKS[@]}"; do
  if brew list --cask "$c" >/dev/null 2>&1; then
    pass "cask: $c"
  else
    fail "cask: $c"
  fi
done

# ChatGPT desktop is Apple Silicon + macOS 14+ only
if [[ "$(uname -m)" == "arm64" ]] && [[ "$(sw_vers -productVersion | cut -d. -f1)" -ge 14 ]]; then
  if brew list --cask chatgpt >/dev/null 2>&1; then
    pass "cask: chatgpt"
  else
    fail "cask: chatgpt"
  fi
else
  echo "  - skipping chatgpt (requires Apple Silicon + macOS 14+)"
fi

echo "==> Stow symlinks"
for f in "$HOME/.zshrc" "$HOME/.gitconfig"; do
  if [[ -L "$f" ]]; then
    target="$(readlink "$f")"
    case "$target" in
      /*) resolved="$target" ;;
      *) resolved="$HOME/$target" ;;
    esac
    resolved="$(cd "$(dirname "$resolved")" && pwd -P)/$(basename "$resolved")"
    if [[ "$resolved" == "$DOTFILES_DIR"/* ]]; then
      pass "$f -> $target"
    else
      fail "$f symlink points outside $DOTFILES_DIR ($target)"
    fi
  elif [[ -e "$f" ]]; then
    fail "$f exists but is not a stow symlink into $DOTFILES_DIR"
  else
    fail "$f missing"
  fi
done

if [[ -d "$HOME/.agents/skills" ]]; then
  pass "$HOME/.agents/skills present"
else
  fail "$HOME/.agents/skills missing"
fi

echo "==> Homebrew health"
if brew doctor >/dev/null 2>&1; then
  pass "brew doctor"
else
  echo "  ! brew doctor reported warnings (review manually)"
fi

if [[ "$FAILED" -ne 0 ]]; then
  echo "==> verify.sh: FAILURES detected" >&2
  exit 1
fi
echo "==> verify.sh: all checks passed"
