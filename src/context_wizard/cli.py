"""CLI-интерфейс ContextWizard."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from context_wizard.app import Collector, CollectorOptions
from context_wizard.config import load_setup, resolve_project_root
from context_wizard.output import resolve_output_options
from context_wizard.tui import TextualUI, WizardApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-wizard",
        description="Собирает богатый контекст-промпт из артефактов проекта.",
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="каталог проекта (по умолчанию — текущий)",
    )
    parser.add_argument("--prompt", default=None, help="идентификатор промпта (без интерактива)")
    parser.add_argument(
        "--answer-target",
        default=None,
        metavar="ID",
        help="переопределить приёмник ответа по id плагина (глобального или проектного)",
    )
    parser.add_argument(
        "--user-prompt",
        default=None,
        help="дополнительный текстовый фрагмент, дописываемый к промпту",
    )
    parser.add_argument(
        "--invalidate",
        action="store_true",
        help="очистить кэш проекта (.tmp) перед запуском",
    )
    parser.add_argument("--file-output", default=None, help="каталог для сохранения вложений")
    parser.add_argument(
        "--prompt-output",
        default=None,
        help="каталог для сохранения готового промпта (rich_prompt.txt)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="общий каталог для промпта и вложений (несовместим с --file-output/--prompt-output)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        root = resolve_project_root(args.project)
        output = resolve_output_options(
            prompt_output=args.prompt_output,
            file_output=args.file_output,
            output=args.output,
        )
    except (ValueError, NotADirectoryError) as exc:
        parser.error(str(exc))

    config = load_setup(root)
    options = CollectorOptions(
        output=output,
        prompt_id=args.prompt,
        user_prompt=args.user_prompt,
        invalidate=args.invalidate,
        answer_target_id=args.answer_target,
    )

    app = WizardApp()
    ui = TextualUI(app)
    collector = Collector(root, config, ui)
    app.set_pipeline(lambda: collector.run(options))
    app.run()

    if app.error is not None:
        print(f"Ошибка сборки: {app.error}", file=sys.stderr)
        return 1
    if app.aborted:
        print("Сборка отменена.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
