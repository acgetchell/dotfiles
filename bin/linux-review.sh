#!/usr/bin/env bash
# User-space Linux review tools; never source or modify shell startup files.
set -euo pipefail
umask 077

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository"
mode="${1:-check}"
shift || true
case "$mode" in setup|check|smoke|probe|exec) ;; *) echo "Usage: bin/linux-review.sh {setup|check|smoke|probe|exec COMMAND...}" >&2; exit 2 ;; esac

fail() { echo "linux-review: $*" >&2; exit 2; }
[[ "$(uname -s)" == Linux ]] || fail "Linux required; use just setup for macOS desktop configuration."
architecture="$(uname -m)"
case "$architecture" in x86_64|aarch64) ;; *) fail "Unsupported architecture $architecture; supported candidates: x86_64, aarch64." ;; esac
libc="$(getconf GNU_LIBC_VERSION 2>/dev/null || true)"
[[ "$libc" == 'glibc '* ]] || fail "glibc >= 2.28 required by the locked tool environment; musl/unknown libc is unverified."
libc_version="${libc#glibc }"
libc_major="${libc_version%%.*}"
libc_minor="${libc_version#*.}"
libc_minor="${libc_minor%%.*}"
[[ "$libc_major" =~ ^[0-9]+$ && "$libc_minor" =~ ^[0-9]+$ ]] || fail "Unable to parse glibc version."
(( libc_major > 2 || (libc_major == 2 && libc_minor >= 28) )) || fail "glibc $libc_version is too old; use an approved newer environment."

export DOTFILES_REVIEW_PREFIX="${DOTFILES_REVIEW_PREFIX:-$HOME/.local/share/dotfiles-review}"
export DOTFILES_REVIEW_CACHE="${DOTFILES_REVIEW_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-review}"
export DOTFILES_REVIEW_TMP="${DOTFILES_REVIEW_TMP:-${TMPDIR:-/tmp}/dotfiles-review-$UID}"
export DOTFILES_REVIEW_ARTIFACTS="${DOTFILES_REVIEW_ARTIFACTS:-$repository/target/linux-review}"
export DOTFILES_REVIEW_SKILLS_DIR="${DOTFILES_REVIEW_SKILLS_DIR:-$DOTFILES_REVIEW_PREFIX/skills}"
for directory in "$DOTFILES_REVIEW_PREFIX" "$DOTFILES_REVIEW_CACHE" "$DOTFILES_REVIEW_TMP" "$DOTFILES_REVIEW_ARTIFACTS" "$DOTFILES_REVIEW_SKILLS_DIR"; do
  [[ "$directory" == /* ]] || fail "Directory settings must be absolute paths."
  mkdir -p "$directory" || fail "Directory unavailable; select user-owned storage or scratch."
done
mkdir -p "$DOTFILES_REVIEW_PREFIX/bin"
# Just's shebang recipes also need executable storage, independent of download scratch.
export JUST_TEMPDIR="$DOTFILES_REVIEW_PREFIX/recipe-tmp"
mkdir -p "$JUST_TEMPDIR"
export PATH="$DOTFILES_REVIEW_PREFIX/bin:$PATH"
export UV_CACHE_DIR="$DOTFILES_REVIEW_CACHE/uv"
export UV_PROJECT_ENVIRONMENT="$DOTFILES_REVIEW_PREFIX/venv"
export UV_PYTHON_INSTALL_DIR="$DOTFILES_REVIEW_PREFIX/python"
export TMPDIR="$DOTFILES_REVIEW_TMP"
export XDG_CACHE_HOME="$DOTFILES_REVIEW_CACHE"
# Never create Python shims in ~/.local/bin; site/module Python remains selectable.
export UV_PYTHON_INSTALL_BIN=0
export UV_HTTP_TIMEOUT=30 UV_HTTP_RETRIES=1

for tool in git bash zsh stow; do
  command -v "$tool" >/dev/null || fail "Required tool '$tool' unavailable. Load a site module or ask the environment owner to provide it; no checks were skipped."
done

tool_version() {
  "$1" --version 2>/dev/null | sed -nE 's/^[^0-9]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -1
}

install_release() {
  local tool="$1" version="$2" url="$3" asset="$4" sums="$5" member="${6:-$1}"
  local installed="" stage pending expected actual archive_member
  if command -v "$tool" >/dev/null; then installed="$(tool_version "$tool" || true)"; fi
  [[ "$installed" != "$version" ]] || return 0
  [[ "$mode" == setup ]] || fail "'$tool' missing or wrong version (expected $version). Run bin/linux-review.sh setup on a connected provisioning host."
  for prerequisite in curl tar unzip sha256sum; do
    command -v "$prerequisite" >/dev/null || fail "Provisioning requires '$prerequisite'; load a site tool/module."
  done
  stage="$(mktemp -d "$DOTFILES_REVIEW_TMP/install.XXXXXX")"
  echo "linux-review: installing $tool $version"
  if ! curl --proto '=https' --tlsv1.2 -fsSL --connect-timeout 10 --max-time 120 "$url/$asset" -o "$stage/$asset" \
      || ! curl --proto '=https' --tlsv1.2 -fsSL --connect-timeout 10 --max-time 30 "$url/$sums" -o "$stage/checksums"; then
    rm -rf "$stage"
    fail "Release download unavailable; check the provisioning allowlist/proxy. No successful installation claimed."
  fi
  expected="$(awk -v asset="$asset" '$2 == asset || $2 == "*" asset {print $1}' "$stage/checksums")"
  # Some per-asset checksum files contain only the hash.
  if [[ -z "$expected" && "$sums" == "$asset.sha256" ]]; then expected="$(awk 'NF == 1 {print $1}' "$stage/checksums")"; fi
  actual="$(sha256sum "$stage/$asset")"
  actual="${actual%% *}"
  if [[ ! "$expected" =~ ^[a-fA-F0-9]{64}$ || "$expected" != "$actual" ]]; then
    rm -rf "$stage"
    fail "Release checksum mismatch or missing checksum for $tool."
  fi
  if [[ "$asset" == *.zip ]]; then
    unzip -p "$stage/$asset" "$member" > "$stage/executable"
  else
    archive_member="$(tar -tzf "$stage/$asset" | awk -v member="$member" '$0 == member || $0 ~ "/" member "$" {print}')"
    [[ -n "$archive_member" && "$archive_member" != *$'\n'* ]] || fail "Ambiguous executable in $tool archive."
    tar -xOzf "$stage/$asset" "$archive_member" > "$stage/executable"
  fi
  # Temporary storage may be noexec; validate and rename on the prefix filesystem.
  pending="$(mktemp -d "$DOTFILES_REVIEW_PREFIX/bin/.$tool.XXXXXX")"
  cp "$stage/executable" "$pending/executable"
  chmod 700 "$pending/executable"
  if [[ "$(tool_version "$pending/executable")" != "$version" ]]; then
    rm -rf "$stage" "$pending"
    fail "Downloaded $tool cannot run at the pinned version on this host."
  fi
  mv "$pending/executable" "$DOTFILES_REVIEW_PREFIX/bin/$tool"
  rm -rf "$stage" "$pending"
  hash -r
}

uv_version="$(sed -nE 's/^required-version = "==([0-9]+\.[0-9]+\.[0-9]+)"$/\1/p' pyproject.toml)"
[[ "$uv_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "Invalid uv pin in pyproject.toml."
uv_asset="uv-$architecture-unknown-linux-gnu.tar.gz"
install_release uv "$uv_version" "https://github.com/astral-sh/uv/releases/download/$uv_version" "$uv_asset" "$uv_asset.sha256"
just_version="$(bash bin/resolve-just-version.sh justfile)"
install_release just "$just_version" "https://github.com/casey/just/releases/download/$just_version" \
  "just-$just_version-$architecture-unknown-linux-musl.tar.gz" SHA256SUMS
version="$(just --evaluate dprint_version)"
install_release dprint "$version" "https://github.com/dprint/dprint/releases/download/$version" \
  "dprint-$architecture-unknown-linux-gnu.zip" SHASUMS256.txt
version="$(just --evaluate rumdl_version)"
asset="rumdl-v$version-$architecture-unknown-linux-gnu.tar.gz"
install_release rumdl "$version" "https://github.com/rvben/rumdl/releases/download/v$version" "$asset" "$asset.sha256"

if [[ "$mode" == setup ]]; then
  uv sync --locked --group dev
  # The setup report includes the pinned plugin check for disconnected validation.
  uv run --locked --no-sync python scripts/linux_review.py setup
  echo "linux-review: setup complete. Run bin/linux-review.sh check in the same site/module environment."
  exit 0
fi
export UV_OFFLINE=1 UV_NO_SYNC=1 UV_PYTHON_DOWNLOADS=never
uv sync --locked --group dev --offline --no-python-downloads --check \
  || fail "Locked Python environment is unavailable or out of date. Rerun setup on a connected provisioning host."
case "$mode" in
  exec) [[ $# -gt 0 ]] || fail "exec requires a command."; exec "$@" ;;
  *) exec uv run --locked --no-sync --no-python-downloads python scripts/linux_review.py "$mode" "$@" ;;
esac
