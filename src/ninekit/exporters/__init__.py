"""Exporter registry (DESIGN 7): target name -> module `ninekit.exporters.<target>`.

Each module exposes `export(manifest_path, out_dir, scale=None, runtime=False) -> list[Path]`.
"""
from __future__ import annotations

import importlib
from typing import Callable

from ninekit import NinekitError

TARGETS = ("json", "godot", "unity", "flutter", "css", "phaser")


def get_exporter(target: str) -> Callable:
    """The export() function of [target], with a clear error when the target is unknown or not installed."""
    if target not in TARGETS:
        raise NinekitError(f"unknown export target {target!r} (known: {', '.join(TARGETS)})")
    module_name = f"ninekit.exporters.{target}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name and (module_name == e.name or module_name.startswith(e.name + ".")):
            raise NinekitError(f"export target {target!r} is not available in this ninekit "
                               f"(missing ninekit/exporters/{target}.py)") from None
        raise
    fn = getattr(module, "export", None)
    if not callable(fn):
        raise NinekitError(f"export target {target!r}: {module_name} has no export() function")
    return fn
