from pathlib import Path

from gauss_cli.auth import AUTH_FILE_OVERRIDE_ENV, _auth_file_path


def test_auth_file_path_prefers_override(monkeypatch, tmp_path: Path):
    override = tmp_path / "override-auth.json"
    monkeypatch.setenv(AUTH_FILE_OVERRIDE_ENV, str(override))

    assert _auth_file_path() == override
