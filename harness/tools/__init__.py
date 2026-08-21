"""
Combined tool registry for the harness.

This is the single source of truth the control loop should import from —
rather than each caller needing to know which individual tool module (filesystem,
git, ...) a given tool lives in and manually merging dicts themselves.

Add new tool modules by importing their TOOLS dict and merging it in below.
This is the one file in harness/tools/ you're expected to edit as you add
project-specific tools (e.g. a tool that calls a third-party API your app
depends on) — everything else in this starter kit's engine/ should stay
untouched; project-specific additions belong here or in a new sibling
module imported here, not by editing filesystem.py/git_tool.py/run_command.py.
"""

from harness.tools.filesystem import TOOLS as _FILESYSTEM_TOOLS
from harness.tools.git_tool import TOOLS as _GIT_TOOLS
from harness.tools.run_command import TOOLS as _RUN_COMMAND_TOOLS

ALL_TOOLS: dict = {
    **_FILESYSTEM_TOOLS,
    **_GIT_TOOLS,
    **_RUN_COMMAND_TOOLS,
}
