from pathlib import Path

from app.core.config import default_data_dir


def test_relative_data_dir_is_anchored_to_project_root(monkeypatch):
    relative = Path("test-data") / "neko"
    project_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("NEKO_DATA_DIR", str(relative))
    assert default_data_dir() == (project_root / relative).resolve()


def test_absolute_data_dir_is_preserved_and_normalized(tmp_path, monkeypatch):
    target = tmp_path / "folder" / ".." / "neko"
    monkeypatch.setenv("NEKO_DATA_DIR", str(target))
    assert default_data_dir() == target.resolve()


def test_backend_uses_the_absolute_data_directory_passed_by_electron(tmp_path, monkeypatch):
    electron_data_dir = (tmp_path / "Local" / "NekoAI").resolve()
    monkeypatch.setenv("NEKO_DATA_DIR", str(electron_data_dir))
    assert default_data_dir() == electron_data_dir
