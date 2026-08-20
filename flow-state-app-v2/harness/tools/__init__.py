"""
Combined tool registry for the harness.

This is the single source of truth the control loop should import from —
rather than each caller needing to know which individual tool module (filesystem,
git, ...) a given tool lives in and manually merging dicts themselves.

Add new tool modules by importing their TOOLS dict and merging it in below.
"""

from harness.tools.filesystem import TOOLS as _FILESYSTEM_TOOLS
from harness.tools.git_tool import TOOLS as _GIT_TOOLS
from harness.tools.run_command import TOOLS as _RUN_COMMAND_TOOLS

ALL_TOOLS: dict = {
    **_FILESYSTEM_TOOLS,
    **_GIT_TOOLS,
    **_RUN_COMMAND_TOOLS,
}
