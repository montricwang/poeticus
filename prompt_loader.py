"""Compatibility module: use backend.ai.prompt_loader for new imports."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("backend.ai.prompt_loader")
