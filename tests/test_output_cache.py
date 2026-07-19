from pathlib import Path

import pytest

from context_wizard.cache import Cache
from context_wizard.output import (
    PROMPT_FILENAME,
    OutputOptions,
    RichPromptDTO,
    resolve_delivery_directory,
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


def test_delivery_directory_resolution(tmp_path):
    assert resolve_delivery_directory(OutputOptions(), tmp_path).path == (
        tmp_path / "output"
    ).resolve()
    only_prompt = resolve_delivery_directory(
        OutputOptions(prompt_dir=tmp_path / "prompt"), tmp_path
    )
    assert only_prompt.path == (tmp_path / "prompt").resolve()

    common = resolve_delivery_directory(
        OutputOptions(
            prompt_dir=tmp_path / "out" / "prompts",
            file_dir=tmp_path / "out" / "files" / "raw",
        ),
        tmp_path,
    )
    assert common.path == (tmp_path / "out").resolve()
    assert common.ambiguous is False

    ambiguous = resolve_delivery_directory(
        OutputOptions(
            prompt_dir=tmp_path / "one" / "a" / "b",
            file_dir=tmp_path / "two" / "c" / "d",
        ),
        tmp_path,
    )
    assert ambiguous.path is None
    assert ambiguous.ambiguous is True


def test_write_prompt_to_file_and_copy_attachments(tmp_path):
    attach = tmp_path / ".tmp" / "downloads" / "img.png"
    attach.parent.mkdir(parents=True)
    attach.write_bytes(b"\x89PNG")
    dto = RichPromptDTO(
        prompt="file=.tmp/downloads/img.png",
        attachments=[attach],
        root=tmp_path,
    )

    out_dir = tmp_path / "out"
    opts = resolve_output_options(prompt_output=None, file_output=None, output=str(out_dir))
    result = write_output(dto, opts)

    assert result == out_dir / PROMPT_FILENAME
    assert (out_dir / PROMPT_FILENAME).read_text(encoding="utf-8") == "file=img.png"
    assert (out_dir / "img.png").read_bytes() == b"\x89PNG"


def test_copied_attachment_path_is_relative_to_separate_prompt_dir(tmp_path):
    attach = tmp_path / ".tmp" / "work.zip"
    attach.parent.mkdir()
    attach.write_bytes(b"zip")
    dto = RichPromptDTO(
        prompt="Work: .tmp/work.zip",
        attachments=[attach],
        root=tmp_path,
    )
    prompt_dir = tmp_path / "prompt-out"
    file_dir = tmp_path / "file-out"

    write_output(dto, OutputOptions(prompt_dir=prompt_dir, file_dir=file_dir))

    assert (prompt_dir / PROMPT_FILENAME).read_text(encoding="utf-8") == (
        "Work: ../file-out/work.zip"
    )
    assert (file_dir / "work.zip").read_bytes() == b"zip"


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
