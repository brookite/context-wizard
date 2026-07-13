from context_wizard.state import ArtifactRegistry, Source, VariableStore


def test_higher_priority_source_wins():
    store = VariableStore()
    store.set("name", "from_global", Source.GLOBAL)
    store.set("name", "from_survey", Source.SURVEY)
    assert store.get("name") == "from_survey"
    assert store.source_of("name") == Source.SURVEY


def test_external_tool_beats_survey():
    store = VariableStore()
    store.set("x", "survey", Source.SURVEY)
    store.set("x", "tool", Source.EXTERNAL_TOOL)
    assert store.get("x") == "tool"


def test_lower_priority_does_not_override():
    store = VariableStore()
    store.set("x", "survey", Source.SURVEY)
    store.set("x", "global", Source.GLOBAL)
    assert store.get("x") == "survey"


def test_get_text_coerces_types():
    store = VariableStore()
    store.set("flag", True, Source.GLOBAL)
    store.set("num", 42, Source.GLOBAL)
    assert store.get_text("flag") == "true"
    assert store.get_text("num") == "42"
    assert store.get_text("missing") is None


def test_has_and_names():
    store = VariableStore()
    store.set("a", 1, Source.GLOBAL)
    store.set("b", 2, Source.SURVEY)
    assert store.has("a")
    assert not store.has("c")
    assert store.names() == {"a", "b"}


def test_as_dict_respects_priority():
    store = VariableStore()
    store.set("a", "g", Source.GLOBAL)
    store.set("a", "t", Source.EXTERNAL_TOOL)
    store.set("b", "g", Source.GLOBAL)
    assert store.as_dict() == {"a": "t", "b": "g"}


def test_artifact_registry_dedup_and_order(tmp_path):
    reg = ArtifactRegistry()
    f1 = tmp_path / "a.png"
    f2 = tmp_path / "b.pdf"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    reg.add(f1)
    reg.add(f2)
    reg.add(f1)  # дубликат
    assert len(reg) == 2
    assert reg.attachments[0].name == "a.png"
    assert reg.attachments[1].name == "b.pdf"
    assert f1 in reg
