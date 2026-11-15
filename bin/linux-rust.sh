#!/usr/bin/env bash
# Supply the review fixture's Rust prerequisite without changing a site toolchain.
set -euo pipefail
repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$repository/bin/platform-profile.sh"
select_profile linux-cloud >/dev/null
source "$repository/profiles/linux-cloud.env"
prefix="${DOTFILES_REVIEW_PREFIX:-$HOME/.local/share/dotfiles-review}"
[[ "$prefix" == /* ]] || { echo "DOTFILES_REVIEW_PREFIX must be absolute" >&2; exit 2; }
if [[ -d "$prefix/cargo/bin" ]]; then
  export RUSTUP_HOME="$prefix/rustup" CARGO_HOME="$prefix/cargo"
  export PATH="$CARGO_HOME/bin:$PATH"
fi
if command -v rustc >/dev/null && command -v cargo >/dev/null; then
  if identity="$(rustc --version)" && [[ "$identity" =~ ^rustc\ ([0-9]+)\.([0-9]+)\. ]] && (( BASH_REMATCH[1] > 1 || (BASH_REMATCH[1] == 1 && BASH_REMATCH[2] >= 85) )); then
    exit 0
  fi
fi
export RUSTUP_HOME="$prefix/rustup" CARGO_HOME="$prefix/cargo"
export PATH="$CARGO_HOME/bin:$PATH"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
url="https://static.rust-lang.org/rustup/archive/$DOTFILES_RUSTUP_VERSION/x86_64-unknown-linux-gnu/rustup-init"
curl --proto '=https' --tlsv1.2 -fsSL "$url" -o "$stage/rustup-init"
curl --proto '=https' --tlsv1.2 -fsSL "$url.sha256" -o "$stage/checksum"
expected="$(awk 'NR == 1 {print $1}' "$stage/checksum")"
actual="$(sha256sum "$stage/rustup-init")"
[[ "$expected" =~ ^[a-f0-9]{64}$ && "${actual%% *}" == "$expected" ]] || { echo "Rustup checksum mismatch" >&2; exit 2; }
chmod 700 "$stage/rustup-init"
"$stage/rustup-init" -y --no-modify-path --profile minimal --default-toolchain "$DOTFILES_RUST_VERSION"
