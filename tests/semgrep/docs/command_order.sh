#!/usr/bin/env bash

# ok: dotfiles.docs.check-before-fix-command-order
just check
just fix

# ruleid: dotfiles.docs.check-before-fix-command-order
just fix
just check

# ok: dotfiles.docs.check-before-fix-command-order
just python-check
just python-fix

# ruleid: dotfiles.docs.check-before-fix-command-order
just python-fix
just python-check
