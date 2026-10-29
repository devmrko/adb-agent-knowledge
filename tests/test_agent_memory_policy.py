import json

import pytest

from scripts.configure_agent_memory import apply, inventory, plan, restore


def fixture(home):
    project = home / "projects/demo"
    project.mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Rules\nRun project tests.\n")
    (project / "MEMORY.md").write_text("Unique local knowledge: retain until verified in DB.\n")
    (home / ".claude").mkdir()
    (home / ".claude/settings.json").write_text(
        '{"permissions":{"deny":["example"]},"autoMemoryEnabled":true}'
    )
    return project


def test_preview_preserves_all_originals_and_lists_memory(tmp_path):
    project = fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = plan(tmp_path, [tmp_path, project], False, False)
    assert result["memories"] == [project / "MEMORY.md"]
    assert len(result["changes"]) == 3
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert all("MEMORY.md" != c["path"].name for c in result["changes"])
    assert not (tmp_path / ".local").exists()


def test_apply_is_idempotent_and_restore_preserves_existing_rules_and_settings(tmp_path):
    project = fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = plan(tmp_path, [tmp_path], True, True)
    manifest = apply(result["changes"], tmp_path)
    assert manifest is not None
    assert (project / "AGENTS.md").read_bytes().startswith(before[project / "AGENTS.md"])
    settings = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert settings == {"permissions": {"deny": ["example"]}, "autoMemoryEnabled": False}
    assert plan(tmp_path, [tmp_path], True, True)["changes"] == []
    assert restore(manifest, False) == 4
    assert restore(manifest, True) == 4
    assert all(p.read_bytes() == value for p, value in before.items())
    assert not (tmp_path / ".codex/AGENTS.md").exists()
    assert restore(manifest, True) == 0


def test_restore_refuses_changed_file_before_restoring_any(tmp_path):
    project = fixture(tmp_path)
    manifest = apply(plan(tmp_path, [tmp_path], False, True)["changes"], tmp_path)
    target = project / "AGENTS.md"
    target.write_text(target.read_text() + "New work\n")
    with pytest.raises(ValueError, match="changed after"):
        restore(manifest, True)
    assert (tmp_path / ".codex/AGENTS.md").exists()
    assert "New work" in target.read_text()


def test_symlinks_and_dependencies_are_not_followed(tmp_path):
    project = fixture(tmp_path)
    (project / "CLAUDE.md").symlink_to(project / "MEMORY.md")
    (tmp_path / "alias").symlink_to(project, target_is_directory=True)
    hidden = project / "node_modules/vendor"
    hidden.mkdir(parents=True)
    (hidden / "AGENTS.md").write_text("vendor rule")
    files, _, errors = inventory([tmp_path])
    assert files == [project / "AGENTS.md"] and not errors
    with pytest.raises(ValueError, match="Symlink"):
        plan(tmp_path / "alias", [project], False, False)
    (tmp_path / ".claude/CLAUDE.md").symlink_to(project / "MEMORY.md")
    with pytest.raises(ValueError, match="Symlink"):
        plan(tmp_path, [project], False, False)


def test_invalid_settings_or_markers_fail_before_any_write(tmp_path):
    project = fixture(tmp_path)
    settings = tmp_path / ".claude/settings.json"
    settings.write_text("not json")
    with pytest.raises(ValueError):
        plan(tmp_path, [project], False, True)
    assert not (tmp_path / ".codex").exists()
    settings.write_text("{}")
    (project / "AGENTS.md").write_text("<!-- BEGIN vector-knowledge-memory-policy -->")
    with pytest.raises(ValueError, match="markers"):
        plan(tmp_path, [project], False, True)


def test_apply_refuses_changes_since_plan(tmp_path):
    project = fixture(tmp_path)
    result = plan(tmp_path, [tmp_path], False, False)
    (project / "AGENTS.md").write_text("Concurrent update")
    with pytest.raises(ValueError, match="since planning"):
        apply(result["changes"], tmp_path)
    assert not (tmp_path / ".codex").exists()


def test_policy_updates_preserve_surrounding_instructions(tmp_path):
    fixture(tmp_path)
    apply(plan(tmp_path, [tmp_path], False, False)["changes"], tmp_path)
    global_file = tmp_path / ".codex/AGENTS.md"
    global_file.write_text("Before\n" + global_file.read_text() + "\nAfter")
    apply(plan(tmp_path, [tmp_path], True, False)["changes"], tmp_path)
    text = global_file.read_text()
    assert text.startswith("Before\n") and text.endswith("\nAfter")
    assert text.count("<!-- BEGIN vector-knowledge-global-policy -->") == 1
    assert "The user authorizes selective automatic capture" in text
