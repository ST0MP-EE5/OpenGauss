from gauss_cli import doctor


def test_detect_agent_browser_runtime_prefers_global_install(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

    def fake_which(cmd: str) -> str | None:
        if cmd == "agent-browser":
            return "/usr/local/bin/agent-browser"
        if cmd == "npx":
            return "/usr/local/bin/npx"
        return None

    monkeypatch.setattr(doctor.shutil, "which", fake_which)

    assert doctor._detect_agent_browser_runtime() == (
        True,
        "(browser automation, global install)",
    )


def test_detect_agent_browser_runtime_uses_local_install(monkeypatch, tmp_path):
    local_bin = tmp_path / "node_modules" / ".bin"
    local_bin.mkdir(parents=True)
    (local_bin / "agent-browser").write_text("", encoding="utf-8")

    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(doctor.shutil, "which", lambda _cmd: None)

    assert doctor._detect_agent_browser_runtime() == (
        True,
        "(browser automation, local install)",
    )


def test_detect_agent_browser_runtime_uses_npx_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

    def fake_which(cmd: str) -> str | None:
        if cmd == "npx":
            return "/usr/local/bin/npx"
        return None

    monkeypatch.setattr(doctor.shutil, "which", fake_which)

    assert doctor._detect_agent_browser_runtime() == (
        True,
        "(browser automation via npx fallback)",
    )


def test_detect_agent_browser_runtime_reports_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(doctor.shutil, "which", lambda _cmd: None)

    available, detail = doctor._detect_agent_browser_runtime()

    assert available is False
    assert "npm install" in detail
