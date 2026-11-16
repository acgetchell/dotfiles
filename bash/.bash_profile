# Login and interactive Bash use the same portable PATH and local overrides.
if [ -r "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi
if [ -r "$HOME/.bash_profile.local" ]; then . "$HOME/.bash_profile.local"; fi
