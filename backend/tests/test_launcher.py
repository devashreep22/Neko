import os
import socket
import sys

from app.launcher import (RunInfo, auth_url, find_running_instance, port_is_free,
                          read_run_info, remove_run_info, write_run_info)


def info(pid=1234, port=8765):
    return RunInfo(pid=pid, port=port, token="tok-123")


def test_run_info_roundtrip_and_url(tmp_path):
    write_run_info(tmp_path, info())
    assert read_run_info(tmp_path) == info()
    assert auth_url(info()) == "http://127.0.0.1:8765/auth/start?t=tok-123"
    if sys.platform != "win32":
        assert oct(os.stat(tmp_path / "run.json").st_mode & 0o777) == "0o600"


def test_run_file_is_created_at_resolved_data_directory(tmp_path):
    data_dir = (tmp_path / "nested" / ".." / "NekoAI").resolve()
    write_run_info(data_dir, info())
    assert (data_dir / "run.json").is_file()
    assert read_run_info(data_dir) == info()


def test_missing_or_corrupt_run_file_is_none(tmp_path):
    assert read_run_info(tmp_path) is None
    (tmp_path / "run.json").write_text("{not json")
    assert read_run_info(tmp_path) is None
    (tmp_path / "run.json").write_text('{"pid": 1}')
    assert read_run_info(tmp_path) is None


def test_detects_running_instance(tmp_path):
    write_run_info(tmp_path, info())
    found = find_running_instance(tmp_path, fetch=lambda port: {"status": "running", "app": "nekoai"},
                                  verify=lambda run: run.token == "tok-123")
    assert found == info()


def test_healthy_server_without_matching_token_is_not_reused(tmp_path):
    write_run_info(tmp_path, info())
    found = find_running_instance(tmp_path, fetch=lambda port: {"status": "running", "app": "nekoai"},
                                  verify=lambda run: False, pid_alive=lambda _pid: False)
    assert found is None
    assert not (tmp_path / "run.json").exists()


def test_busy_unmanaged_port_prevents_starting_a_duplicate_backend(tmp_path, monkeypatch):
    import app.main
    import app.launcher as launcher
    from app.core.config import Settings

    monkeypatch.setattr(launcher, "load_settings", lambda: Settings(data_dir=tmp_path, port=8765))
    monkeypatch.setattr(launcher, "configure_logging", lambda _path: None)
    monkeypatch.setattr(launcher, "find_running_instance", lambda _path: None)
    monkeypatch.setattr(launcher, "port_is_free", lambda _host, _port: False)
    monkeypatch.setattr(app.main, "create_app", lambda *args, **kwargs: pytest.fail("duplicate backend started"))
    assert launcher.main() == 2


def test_stale_file_is_removed(tmp_path):
    write_run_info(tmp_path, info())
    assert find_running_instance(tmp_path, fetch=lambda port: None,
                                 pid_alive=lambda _pid: False) is None
    assert not (tmp_path / "run.json").exists()


def test_run_file_is_preserved_while_its_live_server_is_starting(tmp_path):
    write_run_info(tmp_path, info())
    assert find_running_instance(tmp_path, fetch=lambda _port: None,
                                 pid_alive=lambda pid: pid == 1234) is None
    assert read_run_info(tmp_path) == info()


def test_other_program_on_the_port_is_not_mistaken_for_neko(tmp_path):
    write_run_info(tmp_path, info())
    assert find_running_instance(tmp_path, fetch=lambda p: {"status": "ok", "app": "something-else"},
                                 pid_alive=lambda _pid: False) is None
    assert not (tmp_path / "run.json").exists()


def test_remove_only_removes_own_file(tmp_path):
    write_run_info(tmp_path, info(pid=111))
    remove_run_info(tmp_path, only_pid=222)
    assert (tmp_path / "run.json").exists()
    remove_run_info(tmp_path, only_pid=111)
    assert not (tmp_path / "run.json").exists()


def test_port_is_free_detects_busy_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert port_is_free("127.0.0.1", s.getsockname()[1]) is False
    # (a port we just released may be reusable, so we only assert the busy case)
