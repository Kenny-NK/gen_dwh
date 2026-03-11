import subprocess
import sys


def test_scheduler_can_configure_mappers_in_clean_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.services import scheduler; "
                "from sqlalchemy.orm import configure_mappers; "
                "configure_mappers()"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
