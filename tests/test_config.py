import pytest

from context_wizard.config import (
    list_prompts,
    load_global_vars,
    load_prompt_vars,
    load_setup,
    load_vars_file,
    prompt_id_of,
)


def test_load_json_vars_flattens_nested(tmp_path):
    (tmp_path / "vars.json").write_text(
        '{"a": {"b": 1, "c": {"d": "x"}}, "e": 2}', encoding="utf-8"
    )
    result = load_vars_file(tmp_path / "vars.json")
    assert result == {"a.b": 1, "a.c.d": "x", "e": 2}


def test_load_env_vars(tmp_path):
    (tmp_path / "vars.env").write_text(
        "# comment\nexport TOKEN=abc\nNAME=\"John Doe\"\n\nEMPTY=\n", encoding="utf-8"
    )
    result = load_vars_file(tmp_path / "vars.env")
    assert result == {"TOKEN": "abc", "NAME": "John Doe", "EMPTY": ""}


def test_setup_defaults_when_absent(tmp_path):
    config = load_setup(tmp_path)
    assert config.external_tool is None
    assert config.plugins_dir == "plugins"
    assert config.plugin_dirs == ["plugins"]


def test_setup_parsing(tmp_path):
    (tmp_path / "setup.toml").write_text(
        'external_tool = "moodle"\nplugins_dir = "tools"\n\n'
        '[answer_target]\nid = "codex"\nuse_fs = false\n',
        encoding="utf-8",
    )
    config = load_setup(tmp_path)
    assert config.external_tool == "moodle"
    assert config.plugins_dir == "tools"
    assert config.plugin_dirs == ["tools"]
    assert config.answer_target is not None
    assert config.answer_target.id == "codex"
    assert config.answer_target.use_fs is False


def test_setup_parses_ordered_plugin_directories(tmp_path):
    (tmp_path / "setup.toml").write_text(
        'plugins_dir = ["plugins", "../shared/plugins"]\n',
        encoding="utf-8",
    )
    config = load_setup(tmp_path)
    assert config.plugins_dir == ["plugins", "../shared/plugins"]
    assert config.plugin_dirs == ["plugins", "../shared/plugins"]


@pytest.mark.parametrize("value", ["plugins_dir = []\n", 'plugins_dir = ["plugins", ""]\n'])
def test_setup_rejects_empty_plugin_directories(tmp_path, value):
    (tmp_path / "setup.toml").write_text(value, encoding="utf-8")
    with pytest.raises(ValueError, match="plugins_dir"):
        load_setup(tmp_path)


def test_global_vars_from_vars_storage(tmp_path):
    (tmp_path / "custom.json").write_text('{"k": "v"}', encoding="utf-8")
    (tmp_path / "setup.toml").write_text('vars_storage = "custom.json"\n', encoding="utf-8")
    config = load_setup(tmp_path)
    assert load_global_vars(tmp_path, config) == {"k": "v"}


def test_prompt_vars_and_listing(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "task.md").write_text("body", encoding="utf-8")
    (tmp_path / "env").mkdir()
    (tmp_path / "env" / "task.json").write_text('{"x": 1}', encoding="utf-8")

    prompts = list_prompts(tmp_path)
    assert [p.name for p in prompts] == ["task.md"]
    assert prompt_id_of(prompts[0]) == "task"
    assert load_prompt_vars(tmp_path, "task") == {"x": 1}


def test_unsupported_vars_extension(tmp_path):
    (tmp_path / "vars.yaml").write_text("k: v", encoding="utf-8")
    with pytest.raises(ValueError):
        load_vars_file(tmp_path / "vars.yaml")
