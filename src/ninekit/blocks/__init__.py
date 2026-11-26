"""Block registry (DESIGN 2.3): a block name maps to "module:function", imported only when used."""
from __future__ import annotations

import importlib
from typing import Callable

from ninekit import NinekitError

REGISTRY: dict[str, str] = {
    "casual_button": "ninekit.blocks.casual_button:render",
}


def get_block(name: str) -> Callable:
    """The render(params, scale) function of block [name], with a clear error when it is unknown or missing."""
    if name not in REGISTRY:
        raise NinekitError(f"unknown block {name!r} (known: {', '.join(sorted(REGISTRY)) or 'none'})")
    target = REGISTRY[name]
    module_name, _, func_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name and (module_name == e.name or module_name.startswith(e.name + ".")):
            raise NinekitError(f"block {name!r}: its module {module_name} is not installed "
                               f"(expected {module_name.replace('.', '/')}.py)") from None
        raise
    fn = getattr(module, func_name or "render", None)
    if not callable(fn):
        raise NinekitError(f"block {name!r}: {module_name} has no function {func_name or 'render'}()")
    return fn


def block_defaults(name: str) -> dict | None:
    """The DEFAULTS mapping of block [name]'s module, or None when it has none (DESIGN 2.3: a string param is
    evaluated as an expression only where the default is a number)."""
    fn = get_block(name)
    module = importlib.import_module(fn.__module__)
    d = getattr(module, "DEFAULTS", None)
    return d if isinstance(d, dict) else None
