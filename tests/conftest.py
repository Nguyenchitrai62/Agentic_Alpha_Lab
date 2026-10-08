# Load torch before test modules import pandas on Windows (c10.dll load order).
import sys
from pathlib import Path

import torch

import pytest

_RESEARCH = (Path(__file__).resolve().parents[1] / "research").as_posix().lower()


def _purge_research_modules() -> None:
    """Drop cached modules that were imported from research/ folders.

    Many research tests put their own folder on sys.path and import generic module names (tilt_rule, run_engine,
    analyze, ...). In one pytest process the first folder's module would otherwise be reused by every later test
    with the same module name (ImportError / wrong numbers). Purging before each test module is collected makes
    every test import the module from its own folder, exactly as when it runs alone.
    """
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and Path(f).resolve().as_posix().lower().startswith(_RESEARCH):
            sys.modules.pop(name, None)


@pytest.hookimpl(tryfirst=True)
def pytest_collectstart(collector):
    if isinstance(collector, pytest.Module):
        _purge_research_modules()
