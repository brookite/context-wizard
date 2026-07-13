# ContextWizard

Собирает «богатый» контекст-промпт из артефактов проекта: шаблонизированного промпта,
файлов (inline или вложения), переменных из нескольких источников, кастомных опросников
и внешних инструментов (плагинов). Результат — `RichPromptDTO` (текст промпта + список
вложений + корень проекта), который выводится в stdout/файл либо передаётся плагину-приёмнику.

> Этап 1 (текущий): само приложение. Moodle-модуль сбора контекста и конкретные плагины —
> следующий этап; сейчас система плагинов представлена интерфейсами и загрузчиком папки.

## Установка и запуск

```bash
uv sync
uv run context-wizard <каталог-проекта> [--output <dir>]
# или
uv run python -m context_wizard examples/demo --output out
```

Без `--prompt` откроется TUI (Textual) для выбора промпта и прохождения опросника.

### CLI-флаги
- `<project>` — каталог проекта (по умолчанию текущий).
- `--prompt <id>` — выбрать промпт без интерактива (id = имя файла без расширения).
- `--answer-target <id>` — переопределить приёмник ответа по id плагина (должен быть
  установлен глобально или в проекте); например `--answer-target codex`.
- `--user-prompt <text>` — дописать текстовый фрагмент к промпту.
- `--invalidate` — очистить кэш `.tmp/` перед запуском.
- `--prompt-output <dir>` — сохранить промпт как `rich_prompt.txt` (иначе stdout).
- `--file-output <dir>` — скопировать вложения в каталог.
- `--output <dir>` — общий каталог для промпта и вложений (несовместим с двумя предыдущими).

## Структура проекта

```
project/
  setup.toml        # дескриптор проекта (опционально)
  vars.json|.env    # глобальные переменные
  tools.env         # секреты/окружение для инструментов
  prompts/          # шаблоны промптов (*.txt, *.md, …)
  env/              # переменные для конкретного промпта: <prompt>.{json,env}
  surveys/          # кастомные опросники: <prompt>.json
  plugins/          # локальные плагины (drop-in *.py)
  assets/           # произвольные файлы
  references/       # произвольные материалы
  .tmp/             # кэш (очищается --invalidate)
```

## Синтаксис шаблонов

- `{{ name }}` — подстановка текстовой переменной. Идентификатор — как в Python, плюс
  символы `# . , / \ ;` (например, `{{ project.name }}`).
- `{{ file: path }}` — текстовый файл встраивается inline; бинарный/папка → относительный
  путь и регистрация во вложениях. Поддерживает `$NAME` / `$(NAME)` в пути
  (например, `{{ file: $DIR/notes.txt }}`).
- `{{ @path }}` — всегда относительный путь (без inline), регистрируется во вложениях;
  `$` не разворачивается.

## Приоритет переменных

При совпадении имени побеждает более интерактивный/поздний источник:

```
внешний инструмент > опросник > env/<prompt> > глобальные vars
```

## Опросники

`surveys/<prompt>.json` — массив вопросов (`input` / `option` / `multi selection`) с
валидацией по JSON Schema и приведением типов (`int`, `float`, `bool`, `url`, `email`,
`phone`, `path`, `string`). Поля, неприменимые к типу ответа, отсекаются с предупреждением.
Ответы с `"cached": true` сохраняются в `.tmp/` между запусками.

## Плагины

Плагин — это `.py`, где класс задаёт атрибут `id` и наследует `ExternalTool`/`StagedTool`
или `AnswerTarget`. Обнаруживаются во время выполнения из двух мест:

- **глобальные/встроенные** — каталог исходников `src/context_wizard/builtins/` (доступны
  всем проектам; сюда же «устанавливаются» ваши глобальные плагины; тут лежит встроенный
  `codex`);
- **проектные** — один или несколько каталогов из `plugins_dir` в `setup.toml`:

```toml
plugins_dir = ["plugins", "D:/shared/context-wizard/examples/moodle/plugins"]
```

Каталоги загружаются слева направо. При совпадении `id` более поздний проектный плагин
переопределяет ранний, а любой проектный — глобальный.

**Простой инструмент** — один метод:

```python
class MyTool(ExternalTool):
    id = "my"
    def run(self, ctx):        # ctx: PluginContext
        return {"var": "value"}
```

**Многоэтапный инструмент** — конечный автомат `Stage` с ветвлением `next` и кэшем `cached`:

```python
class Moodle(StagedTool):
    id = "moodle"
    initial = "course"
    def stages(self):
        return [Stage("course", self._course), Stage("task", self._task)]
    def _course(self, ctx):
        courses = fetch_courses(ctx.env["MOODLE_TOKEN"])
        cid = ctx.ask_option("Курс?", [c.name for c in courses])   # переиспользует TUI
        return {"course_id": cid}                                   # виден следующему этапу
    def _task(self, ctx):
        return {"task_id": ctx.ask_option("Задание?", fetch_tasks(ctx.store.get("course_id")))}
```

`PluginContext` даёт три уровня взаимодействия:
- **высокий** — `ctx.ask_input/ask_option/ask_multi`, `ctx.run_survey(survey, resolve_options=…,
  on_answer=…, should_ask=…)`, `ctx.load_survey(path)`, `ctx.notify(msg)`;
- **низкий** — `ctx.push_screen(screen)` (свой Textual-экран) и `ctx.app`;
- **данные/состояние** — `ctx.store`, `ctx.scratch` (между этапами), `ctx.env`, `ctx.settings`,
  `ctx.cache` (персистентный, `.tmp/tools/<id>.json`), `ctx.root`, `ctx.use_fs`.

Значения этапов сразу попадают в `store` (слой `EXTERNAL_TOOL`), поэтому поздние этапы
видят ответы ранних.

### Встроенный плагин: доставка в Codex CLI

`codex` (`src/context_wizard/builtins/codex_target.py`) — встроенный глобальный `AnswerTarget`:
создаёт рабочую папку для ответа, копирует туда вложения с сохранением относительной
структуры, кладёт промпт в `PROMPT.md` и открывает Codex CLI в отдельном окне с рабочим
корнем = этой папке. Базовая папка берётся из переменной `CODEX_WORKSPACE` (в `tools.env`)
или из `settings.workspace_dir`. Копировать в проект не нужно — включается в `setup.toml`:

```toml
[answer_target]
id = "codex"
use_fs = true
[answer_target.settings]
workspace_env = "CODEX_WORKSPACE"   # либо workspace_dir = "путь"
# launch = false                    # только подготовить папку, не открывать Codex
```

Готовый пример — `examples/codex/`:

```bash
uv run context-wizard examples/codex --prompt task
```

## Разработка

```bash
uv run pytest        # тесты (в т.ч. TUI через Textual Pilot)
uv run ruff check .  # линт
uv run pyright       # типы
```
