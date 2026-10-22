"""Supplier layout parsers.

Each module defines NAME, matches(text) -> bool and parse(text, file) -> Document.
Public parsers live in this package; your own (e.g. for your personal invoice template) can live in a private
folder set as `parsers_dir` in the config, and are loaded next to these and tried first.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import pkgutil
from types import ModuleType

PARSERS: list[ModuleType] = [
    importlib.import_module(f"{__name__}.{m.name}")
    for m in pkgutil.iter_modules(__path__)
    if not m.name.startswith("_")
]
_loaded_dirs: set[str] = set()


def load_dir(folder: str) -> list[str]:
    """Load every parser module in a folder (once). Returns the names loaded."""
    folder = os.path.realpath(os.path.expanduser(folder))
    if folder in _loaded_dirs or not os.path.isdir(folder):
        return []
    _loaded_dirs.add(folder)
    names = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".py") and not f.startswith("_"):
            spec = importlib.util.spec_from_file_location(f"invoices_pt_private_parsers.{f[:-3]}", os.path.join(folder, f))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            PARSERS.insert(0, module)
            names.append(module.NAME)
    return names


def find(text: str) -> ModuleType | None:
    return next((p for p in PARSERS if p.matches(text)), None)
