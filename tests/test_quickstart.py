"""Static checks for the documented Windows quickstart workflow."""

from pathlib import Path


def test_quickstart_sets_up_environment_tests_database_and_server() -> None:
    script = (Path(__file__).parents[1] / "quickstart.bat").read_text(encoding="utf-8")

    assert "py -3 -m venv .venv" in script
    assert "%VENV_PYTHON% -m pip install -r requirements.txt" in script
    assert "%VENV_PYTHON% -m pytest" in script
    assert "%VENV_PYTHON% project.py init-db" in script
    assert "%VENV_PYTHON% project.py serve" in script
    assert "--no-serve" in script
