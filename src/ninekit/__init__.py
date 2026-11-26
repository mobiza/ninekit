"""ninekit: engine-agnostic sprite generator for game and app UI (see docs/DESIGN.md)."""

__version__ = "0.1.0"


class NinekitError(Exception):
    """A user-facing error (bad spec, missing file, unknown target...): printed without a traceback."""
