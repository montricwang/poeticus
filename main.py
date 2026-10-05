"""Compatibility model import and example script."""

if __name__ == "__main__":
    from runpy import run_module
    run_module("backend.ai.model", run_name="__main__")
else:
    import sys
    from importlib import import_module
    sys.modules[__name__] = import_module("backend.ai.model")
