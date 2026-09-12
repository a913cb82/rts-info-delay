"""Compatibility shim (refactor): the shared-name imports used by tests/
benchmarks now resolve to a concrete era core. Brains live in packages
(src/bots/<name>/{brain,core}.py) and each has its own core copy."""
from .aggressive.intel import *  # noqa: F401,F403
from .aggressive.scout import *  # noqa: F401,F403
from .aggressive.threat import *  # noqa: F401,F403
from .aggressive.raid import *  # noqa: F401,F403
from .aggressive.settle import *  # noqa: F401,F403
from .aggressive.economy import *  # noqa: F401,F403
from .aggressive.protocol import *  # noqa: F401,F403  # noqa: F401,F403
