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

echo "==> CLI tools (not Homebrew-managed)"
NON_BREW_TOOLS=(
  cargo   # rustup toolchain
  rustc   # rustup toolchain
  just    # cargo-installed (bin/bootstrap.sh)
  zizmor  # cargo-installed (bin/bootstrap.sh)
  ssh     # macOS system binary
)
for tool in "${NON_BREW_TOOLS[@]}"; do
  if command -v "$tool" >/dev/null 2>&1; then
    pass "$tool"
  else
    fail "$tool not on PATH"
  fi
done

echo "==> Brewfile CLI tools"
if ! BUNDLE_FORMULAE="$(HOMEBREW_NO_AUTO_UPDATE=1 brew bundle list --formula --file="$DOTFILES_DIR/Brewfile")"; then
  BUNDLE_FORMULAE=""
  fail "could not read formulae from $DOTFILES_DIR/Brewfile"
fi
if ! BUNDLE_CASKS="$(HOMEBREW_NO_AUTO_UPDATE=1 brew bundle list --cask --file="$DOTFILES_DIR/Brewfile")"; then
  BUNDLE_CASKS=""
  fail "could not read casks from $DOTFILES_DIR/Brewfile"
fi

# "Brewfile entry:binary" pairs. A pair is only checked when its entry is
# still declared in the Brewfile, so removing an entry there never causes a
# false failure here.
BREW_BIN_PAIRS=(
  "1password-cli:op"
  "actionlint:actionlint"
  "ansible:ansible"
  "azure-cli:az"
  "docker-desktop:docker"
  "dotnet:dotnet"
  "gh:gh"
  "git:git"
  "git-lfs:git-lfs"
  "gitleaks:gitleaks"
  "gnupg:gpg"
  "gnuplot:gnuplot"
  "helm:helm"
  "jq:jq"
  "kubernetes-cli:kubectl"
  "markdownlint-cli:markdownlint"
  "node:node"
  "pandoc:pandoc"
  "pkgx:pkgx"
  "powershell:pwsh"
  "pylint:pylint"
  "python@3.14:python3"
  "ripgrep:rg"
  "rustup:rustup"
  "shfmt:shfmt"
  "stow:stow"
  "tailscale-app:tailscale"
  "uv:uv"
  "visual-studio-code:code"
  "zola:zola"
)
for pair in "${BREW_BIN_PAIRS[@]}"; do
  entry="${pair%%:*}"
  bin="${pair##*:}"
  if grep -Fxq "$entry" <<< "$BUNDLE_FORMULAE"; then
    kind="formula"
  elif grep -Fxq "$entry" <<< "$BUNDLE_CASKS"; then
    kind="cask"
  else
    continue
  fi
  if ! brew list "--$kind" "$entry" >/dev/null 2>&1; then
    fail "$kind: $entry not installed"
    continue
  fi
  if command -v "$bin" >/dev/null 2>&1; then
    pass "$bin ($entry)"
  else
    fail "$bin ($entry) not on PATH"
  fi
done

echo "==> Casks"
if [[ -z "$BUNDLE_CASKS" ]]; then
  fail "could not read casks from $DOTFILES_DIR/Brewfile"
fi
while IFS= read -r c; do
  [[ -n "$c" ]] || continue
  # ChatGPT desktop is Apple Silicon + macOS 14+ only
  if [[ "$c" == "chatgpt" ]] && ! { [[ "$(uname -m)" == "arm64" ]] && [[ "$(sw_vers -productVersion | cut -d. -f1)" -ge 14 ]]; }; then
    echo "  - skipping chatgpt (requires Apple Silicon + macOS 14+)"
    continue
  fi
  if brew list --cask "$c" >/dev/null 2>&1; then
    pass "cask: $c"
  else
    fail "cask: $c"
  fi
done <<< "$BUNDLE_CASKS"

echo "==> Stow symlinks"
if command -v uv >/dev/null 2>&1; then
  if (cd "$DOTFILES_DIR" && DOTFILES_DIR="$DOTFILES_DIR" uv run python scripts/stow_verify.py); then
    pass "scripts/stow_verify.py"
  else
    fail "stow symlink verification failed (see above)"
  fi
else
  fail "uv not on PATH; cannot run scripts/stow_verify.py"
fi

echo "==> Homebrew health"
if brew doctor >/dev/null 2>&1; then
  pass "brew doctor"
else
  echo "  ! brew doctor reported warnings (review manually)"
fi

# Surface missing formula dependencies. Warn-only: some casks (e.g. mactex)
# declare Homebrew deps they actually bundle themselves.
MISSING_DEPS="$(brew missing 2>/dev/null || true)"
if [[ -z "$MISSING_DEPS" ]]; then
  pass "brew missing: none"
else
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    echo "  ! brew missing: $line"
  done <<< "$MISSING_DEPS"
fi

if [[ "$FAILED" -ne 0 ]]; then
  echo "==> verify.sh: FAILURES detected" >&2
  exit 1
fi
echo "==> verify.sh: all checks passed"
