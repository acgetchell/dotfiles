#!/usr/bin/env bash
# Replay a whole-repository style review with and without a required file header.
set -euo pipefail

scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
repo="$scratch/repository"
inventory="$scratch/rust-paths"
member="crates/helper"
module="$member/src/new_module.rs"
mkdir -p "$repo/$member/src"

cat > "$repo/Cargo.toml" <<'TOML'
[workspace]
members = ["crates/helper"]
resolver = "3"

[workspace.lints.rust]
unsafe_code = "forbid"
TOML
cat > "$repo/$member/Cargo.toml" <<'TOML'
[package]
name = "file-conventions-fixture"
version = "0.1.0"
edition = "2024"

[lints]
workspace = true
TOML
cat > "$repo/$member/src/lib.rs" <<'RS'
#![forbid(unsafe_code)]

pub mod new_module;
RS

git -C "$repo" init --quiet
git -C "$repo" add -- "$member/src/lib.rs"
cat > "$repo/$module" <<'RS'
pub fn answer() -> u8 {
    42
}
RS
git -C "$repo" ls-files -z --cached --others --exclude-standard -- '*.rs' > "$inventory"

check_cargo() {
    cargo clippy --manifest-path "$repo/Cargo.toml" --target-dir "$scratch/target" --locked --offline --all-targets -- -D warnings
}

check_file_conventions() {
    if [[ -f "$repo/check-headers.sh" ]]; then
        (cd "$repo" && bash check-headers.sh < "$inventory")
    fi
}

printf '%s\n' 'Unsafe code is forbidden through the workspace Cargo lint.' > "$repo/AGENTS.md"
cargo generate-lockfile --manifest-path "$repo/Cargo.toml" --offline
check_cargo
findings=$(check_file_conventions)
[[ -z "$findings" ]]
printf '%s\n' 'Cargo-only policy passed without a per-file finding.'

cat > "$repo/AGENTS.md" <<'POLICY'
Every reviewed Rust file must begin with `#![forbid(unsafe_code)]`.
Run `bash check-headers.sh` with the captured NUL-delimited Rust paths on stdin.
POLICY
cat > "$repo/check-headers.sh" <<'CHECKER'
#!/usr/bin/env bash
set -euo pipefail
status=0
while IFS= read -r -d '' path; do
    first_line=
    IFS= read -r first_line < "$path" || true
    if [[ "$first_line" != '#![forbid(unsafe_code)]' ]]; then
        printf '%s:1\n' "$path"
        status=1
    fi
done
exit "$status"
CHECKER

# The Rust inventory and Cargo result are still valid for these source bytes.
status=0
findings=$(check_file_conventions) || status=$?
if [[ "$status" != 1 || "$findings" != "$module:1" ]]; then
    printf 'Expected one missing header at %s:1, got status %s and output %q\n' "$module" "$status" "$findings" >&2
    exit 1
fi
printf 'Missing required file header at %s. Cargo Clippy passed for the same Rust source.\n' "$findings"

{
    printf '#![forbid(unsafe_code)]\n\n'
    cat "$repo/$module"
} > "$scratch/new_module.rs"
mv "$scratch/new_module.rs" "$repo/$module"
findings=$(check_file_conventions)
[[ -z "$findings" ]]
check_cargo
printf '%s\n' 'Restored header passed the repository checker and Cargo Clippy.'
