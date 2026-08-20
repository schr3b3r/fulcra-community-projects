"""Make the app/ directory importable as top-level modules (e.g. `import main`)
regardless of where pytest is invoked from, without needing an `__init__.py`
(which would turn `app/` into a package and complicate the sandboxed layout).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
