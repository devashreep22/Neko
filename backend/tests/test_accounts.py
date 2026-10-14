import json

from app.accounts import account_path, ensure_demo_account


def test_account_initialization_is_create_once(tmp_path):
    ensure_demo_account(tmp_path)
    path = account_path(tmp_path)
    first = json.loads(path.read_text(encoding="utf-8"))
    first["users"][0]["password_hash"] = "intentionally-changed-existing-hash"
    path.write_text(json.dumps(first), encoding="utf-8")
    before = path.read_bytes()

    ensure_demo_account(tmp_path)

    assert path.read_bytes() == before
    assert "NekoDemo" not in path.read_text(encoding="utf-8")
