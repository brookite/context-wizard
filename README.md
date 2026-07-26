# ContextWizard

Builds a "rich" context prompt from project artifacts: a templated prompt, files
(inline or attachments), variables from multiple sources, custom surveys, and external
tools (plugins). The result is a `RichPromptDTO` (prompt text + attachment list +
project root), written to stdout/a file or passed to an answer-target plugin.

## Installation and usage

```bash
uv sync
uv run context-wizard <project-directory> [--output <dir>]
# or
uv run python -m context_wizard examples/demo --output out
```

Without `--prompt`, a Textual TUI opens to select a prompt and complete its survey.

### CLI flags

- `<project>` — project directory (the current directory by default).
- `--prompt <id>` — select a prompt non-interactively (the id is the file name without
  its extension).
- `--answer-target <id>` — override answer targets by plugin id; repeat the flag as
  needed, for example `--answer-target codex --answer-target folder`.
- `--user-prompt <text>` — append a text fragment to the prompt.
- `--invalidate` — clear the `.tmp/` cache before running.
- `--prompt-output <dir>` — save the prompt as `rich_prompt.txt` (stdout otherwise).
- `--file-output <dir>` — copy attachments into a directory.
- `--output <dir>` — shared directory for the prompt and attachments (incompatible with
  the previous two options).

## Project structure

```
project/
  setup.toml        # project descriptor (optional)
  vars.json|.env    # global variables
  tools.env         # secrets/environment for tools
  prompts/          # prompt templates (*.txt, *.md, …)
  env/              # variables for a specific prompt: <prompt>.{json,env}
  surveys/          # custom surveys: <prompt>.json
  plugins/          # local plugins (drop-in *.py files)
  assets/           # arbitrary files
  references/       # arbitrary materials
  .tmp/             # cache (cleared by --invalidate)
```

## Template syntax

- `{{ name }}` — substitute a text variable. An identifier follows Python naming rules,
  with the additional characters `# . , / \ ;` (for example, `{{ project.name }}`).
- `{{ file: path }}` — embed a text file inline; a binary file or directory becomes a
  relative path and is registered as an attachment. Supports `$NAME` / `$(NAME)` in the
  path (for example, `{{ file: $DIR/notes.txt }}`).
- `{{ @path }}` — always use a relative path (never inline) and register it as an
  attachment; `$` is not expanded.

## Variable precedence

When names conflict, the more interactive/later source wins:

```
external tool > survey > env/<prompt> > global vars
```

## Surveys

`surveys/<prompt>.json` is an array of questions (`input` / `option` / `multi selection`)
with JSON Schema validation and type coercion (`int`, `float`, `bool`, `url`, `email`,
`phone`, `path`, `string`). Fields that do not apply to an answer type are discarded with a
warning. Answers with `"cached": true` are stored in `.tmp/` between runs.

## Plugins

A plugin is a `.py` file whose class defines an `id` attribute and inherits from
`ExternalTool`/`StagedTool` or `AnswerTarget`. They are discovered at runtime in two places:

- **global/built-in** — the `src/context_wizard/builtins/` source directory (available to
  every project; this is also where your global plugins are "installed"; it contains the
  built-in `codex` plugin);
- **project-specific** — one or more directories from `plugins_dir` in `setup.toml`:

```toml
plugins_dir = ["plugins", "D:/shared/context-wizard/examples/moodle/plugins"]
```

Directories load from left to right. When ids conflict, a later project-specific plugin
overrides an earlier one, and any project-specific plugin overrides a global plugin.

**A simple tool** has a single method:

```python
class MyTool(ExternalTool):
    id = "my"
    def run(self, ctx):        # ctx: PluginContext
        return {"var": "value"}
```

**A multi-stage tool** is a `Stage` state machine with branching `next` and cached values:

```python
class Moodle(StagedTool):
    id = "moodle"
    initial = "course"
    def stages(self):
        return [Stage("course", self._course), Stage("task", self._task)]
    def _course(self, ctx):
        courses = fetch_courses(ctx.env["MOODLE_TOKEN"])
        cid = ctx.ask_option("Course?", [c.name for c in courses])  # reuses the TUI
        return {"course_id": cid}                                    # visible to next stage
    def _task(self, ctx):
        return {"task_id": ctx.ask_option("Task?", fetch_tasks(ctx.store.get("course_id")))}
```

`PluginContext` provides three interaction levels:

- **high-level** — `ctx.ask_input/ask_option/ask_multi`, `ctx.run_survey(survey, resolve_options=…,
  on_answer=…, should_ask=…)`, `ctx.load_survey(path)`, `ctx.notify(msg)`;
- **low-level** — `ctx.push_screen(screen)` (a custom Textual screen) and `ctx.app`;
- **data/state** — `ctx.store`, `ctx.scratch` (between stages), `ctx.env`, `ctx.settings`,
  `ctx.cache` (persistent, `.tmp/tools/<id>.json`), `ctx.root`, `ctx.use_fs`.

Stage values are immediately added to `store` (the `EXTERNAL_TOOL` layer), so later stages
can access answers from earlier ones.

### Multiple answer targets

The legacy single `[answer_target]` remains supported. To deliver to multiple targets at
once, use an array of tables; plugins run in parallel and errors are reported after all
targets have finished:

```toml
[[answer_targets]]
id = "codex"
use_fs = true

[[answer_targets]]
id = "folder"
use_fs = true
```

You cannot specify both `answer_target` and `answer_targets`. If at least one target has
`use_fs = false`, the shared prompt is rendered without filesystem access.

### Built-in plugin: deliver to Codex CLI

`codex` (`src/context_wizard/builtins/codex_target.py`) is a built-in global
`AnswerTarget`: it creates a response workspace, copies attachments into it while preserving
their relative structure, writes the prompt to `PROMPT.md`, and opens Codex CLI in a separate
window with that workspace as its working root. Base-directory precedence is:
`settings.workspace_dir`, the `CODEX_WORKSPACE` variable (in `tools.env`), the directory from
output flags, then `<project>/output`. You do not need to copy it into the project—enable it
in `setup.toml`:

```toml
[answer_target]
id = "codex"
use_fs = true
[answer_target.settings]
workspace_env = "CODEX_WORKSPACE"   # or workspace_dir = "path"
# launch = false                    # prepare the folder only; do not open Codex
```

If distinct `--prompt-output` and `--file-output` paths are given, their closest common
parent is used provided it is no more than two levels above either directory. If no such
parent exists and `CODEX_WORKSPACE` is not set, Codex asks you to set the variable explicitly.

### Built-in plugin: open the prompt folder

`folder` prepares a separate directory with `PROMPT.md` and attachments, then opens it in
Explorer, Finder, or a Linux file manager. Without output flags, `<project>/output` is used;
`--output`, `--prompt-output`, and `--file-output` follow the same common-parent rules. For
ambiguous separate paths, specify the directory explicitly:

```toml
[[answer_targets]]
id = "folder"
use_fs = true

[answer_targets.settings]
workspace_dir = "prepared-prompts"
```

A complete example is available in `examples/codex/`:

```bash
uv run context-wizard examples/codex --prompt task
```

## Development

```bash
uv run pytest        # tests (including TUI tests via Textual Pilot)
uv run ruff check .  # linting
uv run pyright       # type checking
```
