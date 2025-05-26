"""
samstacks: Deploy a pipeline of AWS SAM stacks

A lightweight Python CLI tool that allows deployment of a pipeline of AWS SAM stacks,
driven by a YAML manifest, following a syntax similar to GitHub Actions.
"""

try:
    from .version import VERSION as __version__
except ImportError:
    # Fallback for development when version.py doesn't exist yet
    try:
        from importlib.metadata import version

        __version__ = version("samstacks")
    except Exception:
        __version__ = "0.0.0-dev"

__author__ = "Alessandro Bologna"
__email__ = "alessandro.bologna@gmail.com"

from .core import Pipeline, Stack
from .exceptions import SamStacksError

__all__ = ["Pipeline", "Stack", "SamStacksError", "__version__"]
