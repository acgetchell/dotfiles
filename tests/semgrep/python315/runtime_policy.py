"""Deliberate policy violations and compliant Python 3.15 counterparts."""

import os
import sys

import yaml


def global_mode() -> dict[str, str]:
    """Global lazy mode is unsafe for the repository's import initialization."""
    # ruleid: dotfiles.python315.no-global-lazy-imports
    sys.set_lazy_imports("all")
    # ruleid: dotfiles.python315.no-global-lazy-imports
    os.environ["PYTHON_LAZY_IMPORTS"] = "all"
    # ruleid: dotfiles.python315.no-global-lazy-imports
    os.putenv("PYTHON_LAZY_IMPORTS", "all")
    # ruleid: dotfiles.python315.no-global-lazy-imports
    return {"PYTHON_LAZY_IMPORTS": "all"}


def normal_mode() -> dict[str, str]:
    """Normal mode respects each module's explicit lazy declarations."""
    # ok: dotfiles.python315.no-global-lazy-imports
    sys.set_lazy_imports("normal")
    # ok: dotfiles.python315.no-global-lazy-imports
    os.environ["PYTHON_LAZY_IMPORTS"] = "normal"
    # ok: dotfiles.python315.no-global-lazy-imports
    os.putenv("PYTHON_LAZY_IMPORTS", "normal")
    # ok: dotfiles.python315.no-global-lazy-imports
    return {"PYTHON_LAZY_IMPORTS": "normal"}


def unsafe_loader() -> None:
    """Constructor and attribute selection bypass Ruff's yaml.load check."""
    # ruleid: dotfiles.skills.safe-yaml-loader
    yaml.Loader("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    yaml.UnsafeLoader("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    yaml.FullLoader("")
    if hasattr(yaml, "CLoader"):
        # ruleid: dotfiles.skills.safe-yaml-loader
        yaml.CLoader("")
    if hasattr(yaml, "CUnsafeLoader"):
        # ruleid: dotfiles.skills.safe-yaml-loader
        yaml.CUnsafeLoader("")
    if hasattr(yaml, "CFullLoader"):
        # ruleid: dotfiles.skills.safe-yaml-loader
        yaml.CFullLoader("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "CLoader", yaml.SafeLoader)("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "CUnsafeLoader", yaml.SafeLoader)("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "CFullLoader", yaml.SafeLoader)("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "Loader", yaml.SafeLoader)("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "UnsafeLoader", yaml.SafeLoader)("")
    # ruleid: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "FullLoader", yaml.SafeLoader)("")


def safe_loader() -> None:
    """Safe C and Python loaders remain allowed, including optional fallback."""
    # ok: dotfiles.skills.safe-yaml-loader
    yaml.SafeLoader("")
    if hasattr(yaml, "CSafeLoader"):
        # ok: dotfiles.skills.safe-yaml-loader
        yaml.CSafeLoader("")
    # ok: dotfiles.skills.safe-yaml-loader
    getattr(yaml, "CSafeLoader", yaml.SafeLoader)("")
