import subprocess

import pytest

from scripts import setup_runtime
from scripts.validate_oracle_installation import guard_schema


def test_core_vs_local_and_remote_runtime_commands():
    core = setup_runtime.commands(False, False)
    assert len(core) == 2 and "--locked" in core[0]
    local = setup_runtime.commands(True, True)
    assert len(local) == 5 and local[2][0].endswith("setup_kev.sh")
    assert local[-1][-1] == "--start-local"
    remote = setup_runtime.commands(False, True)
    assert len(remote) == 4 and not any("--start-local" in c for c in remote)


def test_installation_plan_does_not_mutate_or_download(monkeypatch, capsys):
    monkeypatch.setattr(setup_runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup_runtime.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(
        setup_runtime.sys, "argv", ["setup_runtime", "--with-models", "--verify-models", "--plan"]
    )
    monkeypatch.setattr(
        setup_runtime.subprocess, "run", lambda *a, **kw: pytest.fail("Plan executed a command")
    )
    setup_runtime.main()
    assert "check_model_runtime" in capsys.readouterr().out


def test_unsupported_platform_and_failed_install_stop(monkeypatch):
    with pytest.raises(ValueError, match="WSL"):
        setup_runtime.validate_platform("Windows")
    setup_runtime.validate_platform("Linux")
    setup_runtime.validate_platform("Darwin")
    monkeypatch.setattr(setup_runtime.sys, "argv", ["setup_runtime"])
    monkeypatch.setattr(setup_runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup_runtime.shutil, "which", lambda _: "/usr/bin/git")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "setup")

    monkeypatch.setattr(setup_runtime.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        setup_runtime.main()


@pytest.mark.parametrize("actual,expected", [("ADMIN", "ADMIN"), ("SYS", "SYS"), ("A", "B"), ("A", "")])
def test_oracle_validation_rejects_admin_and_wrong_schema(actual, expected):
    with pytest.raises(ValueError):
        guard_schema(actual, expected)


def test_oracle_validation_accepts_explicit_test_schema():
    guard_schema("AK_TEST_01", "ak_test_01")
