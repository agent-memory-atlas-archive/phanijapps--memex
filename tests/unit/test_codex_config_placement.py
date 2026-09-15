"""notify placement in Codex config.toml: line 3, root table, repaired."""

from pathlib import Path

from memex.infrastructure.harness_installer import install_harness

MARKETPLACE = Path(__file__).parent.parent.parent / "marketplace"


def _install(home: Path, project: Path, config_text: str) -> str:
    project.mkdir(parents=True, exist_ok=True)
    codex = home / ".codex"
    codex.mkdir(parents=True, exist_ok=True)
    if config_text:
        (codex / "config.toml").write_text(config_text, encoding="utf-8")

    # isolated MEMEX_DATA_DIR via monkeypatch in callers; here use env directly
    import os

    old = os.environ.get("MEMEX_DATA_DIR")
    os.environ["MEMEX_DATA_DIR"] = str(home / "memex-data")
    try:
        install_harness("codex", MARKETPLACE, home=home, project=project)
    finally:
        if old is None:
            os.environ.pop("MEMEX_DATA_DIR", None)
        else:
            os.environ["MEMEX_DATA_DIR"] = old
    return (codex / "config.toml").read_text(encoding="utf-8")


def test_notify_inserted_at_line_3(tmp_path: Path) -> None:
    config = _install(
        tmp_path / "home",
        tmp_path / "proj",
        'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "medium"\n'
        'personality = "pragmatic"\n\n[mcp_servers.other]\nurl = "https://x"\n',
    )
    lines = config.splitlines()
    assert lines[2].startswith("notify = ")
    # Root keys stay above the first table; table shifted below notify.
    assert lines[0] == 'model = "gpt-5.6-sol"'
    first_table = next(i for i, line in enumerate(lines) if line.startswith("["))
    assert first_table > 2


def test_misplaced_nested_notify_repaired(tmp_path: Path) -> None:
    """A notify line appended inside a table (our old bug) is moved to line 3."""
    config = _install(
        tmp_path / "home",
        tmp_path / "proj",
        'model = "gpt"\n\n[projects."/x"]\ntrust_level = "trusted"\nnotify = ["/old/wrapper.py"]\n',
    )
    lines = config.splitlines()
    assert lines[2].startswith("notify = ")
    assert sum(line.strip().startswith("notify") for line in lines) == 1
    # The nested copy is gone.
    assert 'notify = ["/old/wrapper.py"]' not in config


def test_already_at_line_3_is_idempotent(tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "proj"
    first = _install(
        home,
        project,
        'model = "a"\nmodel_reasoning_effort = "b"\n'
        'notify = ["%s"]\n' % (home / ".codex/memex-codex-notify.py"),
    )
    second = _install(home, project, first)
    assert second == first


def test_short_config_appends_safely(tmp_path: Path) -> None:
    config = _install(tmp_path / "home", tmp_path / "proj", "")
    lines = config.splitlines()
    assert lines[0].startswith("notify = ")
    assert "[mcp_servers.memex]" in config


def test_mcp_table_appended_after_existing_tables(tmp_path: Path) -> None:
    config = _install(
        tmp_path / "home",
        tmp_path / "proj",
        'model = "gpt"\n\n[projects."/x"]\ntrust_level = "trusted"\n',
    )
    assert config.rstrip().endswith('args = ["serve-mcp"]')
    assert config.index("[mcp_servers.memex]") > config.index("notify = ")
