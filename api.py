"""Compatibility module: use backend.app for new imports."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("backend.app")
