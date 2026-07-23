"""PlatformIO pre-build hook that rejects stale generated pattern assets."""

from pathlib import Path
import subprocess
import sys

Import("env")

project_directory = Path(env.subst("$PROJECT_DIR"))
generator = project_directory / "tools" / "generate_pattern_assets.py"
result = subprocess.run(
    [sys.executable, str(generator), "--check"],
    cwd=project_directory,
    check=False,
)
if result.returncode != 0:
    raise RuntimeError(
        "Generated pattern assets are stale; run "
        "`python3 tools/generate_pattern_assets.py --write`."
    )
