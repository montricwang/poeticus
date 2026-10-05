"""Compatibility module: use backend.ai.context for new imports."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("backend.ai.context")
