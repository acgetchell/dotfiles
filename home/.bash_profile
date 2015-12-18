#!/usr/bin/env bash

# Load RVM, if you are using it
[[ -s $HOME/.rvm/scripts/rvm ]] && source $HOME/.rvm/scripts/rvm

# Add rvm gems and nginx to the path
# export PATH=$PATH:~/.gem/ruby/1.8/bin:/opt/nginx/sbin

# Path to the bash it configuration
export BASH_IT=$HOME/.bash_it

# Lock and Load a custom theme file
# location /.bash_it/themes/
export BASH_IT_THEME='zork'

# Set my editor and git editor
export ATOM_PATH="/Applications"
export EDITOR="/usr/local/bin/atom -w"
export GIT_EDITOR='/usr/local/bin/atom -w'

# Don't check mail when opening terminal.
unset MAILCHECK


# Change this to your console based IRC client of choice.

export IRC_CLIENT='irssi'

# Set this to the command you use for todo.txt-cli

export TODO="t"

# Set vcprompt executable path for scm advance info in prompt (demula theme)
# https://github.com/xvzf/vcprompt
#export VCPROMPT_EXECUTABLE=~/.vcprompt/bin/vcprompt

# Load Bash It
source $BASH_IT/bash_it.sh

# Tell homebrew-cask to put symlinks in default Applications directory
export HOMEBREW_CASK_OPTS="--appdir=/Applications"

# Add Homebrew's sbin
export PATH="/usr/local/sbin:$PATH"

# Setup Python virtualenv
source /usr/local/bin/virtualenvwrapper.sh
export WORKON_HOME=~/.virtualenvs

# Load customization
source ~/.bashrc

[ -s "/Users/adam/.dnx/dnvm/dnvm.sh" ] && . "/Users/adam/.dnx/dnvm/dnvm.sh" # Load dnvm
