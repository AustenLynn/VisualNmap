"""run.sh must hand every VISUALNMAP_* setting through sudo, or the root process silently ignores it."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_sudo_preserves_every_setting_the_app_reads():
    read_by_app = set(re.findall(r'"(VISUALNMAP_[A-Z_]+)"', (REPO / "backend/visualnmap/api.py").read_text()))
    preserved = re.search(r"--preserve-env=(\S+)", (REPO / "run.sh").read_text()).group(1).split(",")
    assert read_by_app - {"VISUALNMAP_IN_CONTAINER"} <= set(preserved)
