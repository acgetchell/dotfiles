#!/usr/bin/env bash
# macos-defaults.sh - apply macOS preferences captured from `defaults read`.
#
# Only keys explicitly set on the source machine are included; keys left at
# macOS factory defaults are intentionally omitted. A few captured values
# happen to match the factory default and are kept so a re-imaged machine
# converges to the same state regardless of its starting point.
#
# Idempotent: safe to re-run. Restarts Dock and Finder at the end; appearance
# changes may require logging out and back in.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macos-defaults.sh only applies to macOS." >&2
  exit 1
fi

echo "==> Appearance"
# Auto light/dark mode (System Settings > Appearance > Auto).
defaults write NSGlobalDomain AppleInterfaceStyleSwitchesAutomatically -bool true

echo "==> Keyboard text input"
# Auto-capitalization and double-space period (match factory defaults; pinned
# so every machine converges to the same behavior).
defaults write NSGlobalDomain NSAutomaticCapitalizationEnabled -bool true
defaults write NSGlobalDomain NSAutomaticPeriodSubstitutionEnabled -bool true

echo "==> Dock"
defaults write com.apple.dock autohide -bool true
defaults write com.apple.dock tilesize -int 48
defaults write com.apple.dock magnification -bool true
defaults write com.apple.dock largesize -int 128
# Minimize windows into their application icon.
defaults write com.apple.dock minimize-to-application -bool true

echo "==> Finder"
# List view for new Finder windows.
defaults write com.apple.finder FXPreferredViewStyle -string "Nlsv"
# New Finder windows open to Recents.
defaults write com.apple.finder NewWindowTarget -string "PfAF"
# Remove items from the Trash after 30 days.
defaults write com.apple.finder FXRemoveOldTrashItems -bool true

echo "==> Trackpad"
# Tap to click and three-finger drag stay off (explicitly pinned).
defaults write com.apple.AppleMultitouchTrackpad Clicking -bool false
defaults write com.apple.AppleMultitouchTrackpad TrackpadThreeFingerDrag -bool false
defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking -bool false

echo "==> Restarting Dock and Finder"
killall Dock 2>/dev/null || true
killall Finder 2>/dev/null || true

echo "==> macos-defaults.sh: done (log out/in for appearance changes)"
