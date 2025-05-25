"""
samstacks: Deploy a pipeline of AWS SAM stacks

A lightweight Python CLI tool that allows deployment of a pipeline of AWS SAM stacks,
driven by a YAML manifest, following a syntax similar to GitHub Actions.
"""

__version__ = "0.1.0"
__author__ = "Alessandro Bologna"
__email__ = "alessandro.bologna@gmail.com"

from .core import Pipeline, Stack
from .exceptions import SamStacksError

__all__ = ["Pipeline", "Stack", "SamStacksError", "__version__"]
