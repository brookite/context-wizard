from pathlib import Path

import pytest

from context_wizard.cache import Cache
from context_wizard.output import (
    PROMPT_FILENAME,
    RichPromptDTO,
    resolve_output_options,
    write_output,
)


def test_output_flag_conflicts():
    with pytest.raises(ValueError):
        resolve_output_options(prompt_output="a", file_output=None, output="b")
    with pytest.raises(ValueError):
        resolve_output_options(prompt_output=None, file_output="a", output="b")


def test_output_flag_resolution():
    opts = resolve_output_options(prompt_output="p", file_output="f", output=None)
    assert opts.prompt_dir == Path("p")
    assert opts.file_dir == Path("f")

    combined = resolve_output_options(prompt_output=None, file_output=None, output="o")
    assert combined.prompt_dir == Path("o")
    assert combined.file_dir == Path("o")


def test_write_prompt_to_file_and_copy_attachments(tmp_path):
    attach = tmp_path / "img.png"
    attach.write_bytes(b"\x89PNG")
    dto = RichPromptDTO(prompt="hello", attachments=[attach], root=tmp_path)

    out_dir = tmp_path / "out"
    opts = resolve_output_options(prompt_output=None, file_output=None, output=str(out_dir))
    result = write_output(dto, opts)

    assert result == out_dir / PROMPT_FILENAME
    assert (out_dir / PROMPT_FILENAME).read_text(encoding="utf-8") == "hello"
    assert (out_dir / "img.png").read_bytes() == b"\x89PNG"


def test_write_prompt_to_stdout(capsys, tmp_path):
    dto = RichPromptDTO(prompt="stdout body", root=tmp_path)
    opts = resolve_output_options(prompt_output=None, file_output=None, output=None)
    result = write_output(dto, opts)
    assert result is None
    assert "stdout body" in capsys.readouterr().out


def test_cache_survey_roundtrip_and_invalidate(tmp_path):
    cache = Cache(tmp_path)
    cache.save_survey_answers("task", {"a": 1, "b": "x"})
    assert cache.load_survey_answers("task") == {"a": 1, "b": "x"}

    cache.invalidate()
    assert cache.load_survey_answers("task") == {}
