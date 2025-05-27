"""
Shared constants for the samstacks package.
"""

import re

# Regex pattern for detecting template strings like ${{ ... }}
TEMPLATE_PATTERN = re.compile(r"^\$\{\{.*\}\}$")
