"""Compatibility shim (refactor): the shared-name imports used by tests/
benchmarks now resolve to a concrete era core. Brains live in packages
(src/bots/<name>/{brain,core}.py) and each has its own core copy."""
from .aggressive.core import *  # noqa: F401,F403
