#!/usr/bin/env bash
# Shared, read-only host selection. Source before any installation effects.

profile_fail() { echo "dotfiles profile: $*" >&2; return 2; }

select_profile() {
  local requested="${1:-auto}" system architecture
  system="$(uname -s)"
  architecture="$(uname -m)"
  if [[ "$requested" == auto ]]; then
    case "$system" in Darwin) requested=macos ;; Linux) requested=linux-cloud ;; *) profile_fail "Unsupported OS: $system"; return 2 ;; esac
  fi
  case "$requested:$system:$architecture" in
    macos:Darwin:arm64|macos:Darwin:x86_64) ;;
    linux-cloud:Linux:x86_64)
      [[ -r /etc/os-release ]] || { profile_fail "Missing /etc/os-release"; return 2; }
      # Read the standard OS identity without executing its contents.
      local distribution release
      distribution="$(sed -nE 's/^ID="?([^" ]+)"?$/\1/p' /etc/os-release)"
      release="$(sed -nE 's/^VERSION_ID="?([^" ]+)"?$/\1/p' /etc/os-release)"
      case "$distribution:$release" in ubuntu:24.04|debian:13|debian:13.*) ;;
        *) profile_fail "Unverified Linux host $distribution $release; supported rebuild profiles: Ubuntu 24.04 / Debian 13 x86_64. Use the separate site-managed linux-review route when appropriate."; return 2 ;;
      esac
      ;;
    *) profile_fail "Profile $requested is unsupported on $system/$architecture; no setup was performed."; return 2 ;;
  esac
  printf '%s\n' "$requested"
}
