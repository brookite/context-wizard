import pytest

from context_wizard.state import Source, VariableStore
from context_wizard.templating import TemplateError, parse_template, render


def make_store(**values: object) -> VariableStore:
    store = VariableStore()
    for name, value in values.items():
        store.set(name, value, Source.GLOBAL)
    return store


def test_plain_variable_substitution(tmp_path):
    store = make_store(name="Alice")
    result = render("Hello {{ name }}!", store=store, root=tmp_path)
    assert result.text == "Hello Alice!"
    assert result.missing == set()


def test_extended_identifier_charset(tmp_path):
    store = make_store(**{"a.b/c": "X"})
    result = render("{{ a.b/c }}", store=store, root=tmp_path)
    assert result.text == "X"


def test_missing_variable_is_recorded_and_blank(tmp_path):
    store = make_store()
    result = render("[{{ absent }}]", store=store, root=tmp_path)
    assert result.text == "[]"
    assert result.missing == {"absent"}


def test_skip_missing_variable(tmp_path):
    store = make_store()
    result = render("[{{ absent }}]", store=store, root=tmp_path, skip=frozenset({"absent"}))
    assert result.text == "[]"
    assert result.missing == set()


def test_file_inline_text(tmp_path):
    (tmp_path / "note.txt").write_text("inlined body", encoding="utf-8")
    store = make_store()
    result = render("{{ file: note.txt }}", store=store, root=tmp_path)
    assert result.text == "inlined body"
    assert result.attachments == []


def test_file_non_text_becomes_attachment(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    store = make_store()
    result = render("see {{ file: pic.png }}", store=store, root=tmp_path)
    assert result.text == "see pic.png"
    assert len(result.attachments) == 1
    assert result.attachments[0].name == "pic.png"


def test_file_folder_becomes_relative_path(tmp_path):
    (tmp_path / "assets").mkdir()
    store = make_store()
    result = render("{{ file: assets }}", store=store, root=tmp_path)
    assert result.text == "assets"
    assert len(result.attachments) == 1


def test_at_sigil_never_inlines_text(tmp_path):
    (tmp_path / "note.txt").write_text("body", encoding="utf-8")
    store = make_store()
    result = render("{{ @note.txt }}", store=store, root=tmp_path)
    assert result.text == "note.txt"
    assert len(result.attachments) == 1


def test_dollar_expansion_in_file_path(tmp_path):
    sub = tmp_path / "1"
    sub.mkdir()
    (sub / "file.txt").write_text("deep", encoding="utf-8")
    store = make_store(NUM="1")
    result = render("{{ file: $NUM/file.txt }}", store=store, root=tmp_path)
    assert result.text == "deep"


def test_dollar_paren_expansion(tmp_path):
    sub = tmp_path / "v2"
    sub.mkdir()
    (sub / "f.txt").write_text("ok", encoding="utf-8")
    store = make_store(DIR="v2")
    result = render("{{ file: $(DIR)/f.txt }}", store=store, root=tmp_path)
    assert result.text == "ok"


def test_at_sigil_does_not_expand_dollar(tmp_path):
    store = make_store(NUM="1")
    # $NUM не разворачивается для @; файла с таким именем нет -> missing
    result = render("{{ @$NUM/file.txt }}", store=store, root=tmp_path)
    assert "$NUM" in result.text
    assert result.missing != set()


def test_use_fs_false_uses_basename_no_inline(tmp_path):
    (tmp_path / "note.txt").write_text("body", encoding="utf-8")
    store = make_store()
    result = render("{{ file: note.txt }}", store=store, root=tmp_path, use_fs=False)
    assert result.text == "note.txt"
    assert result.attachments == []


def test_unknown_namespace_raises(tmp_path):
    store = make_store()
    with pytest.raises(TemplateError):
        render("{{ http: example.com }}", store=store, root=tmp_path)


def test_parse_template_nodes():
    nodes = parse_template("a {{ x }} b")
    assert len(nodes) == 3


def test_missing_file_recorded(tmp_path):
    store = make_store()
    result = render("{{ file: nope.txt }}", store=store, root=tmp_path)
    assert result.missing != set()
