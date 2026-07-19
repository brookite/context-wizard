"""Оркестратор конвейера сборки контекста (Collector)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from context_wizard.cache import Cache
from context_wizard.config import (
    AnswerTargetConfig,
    SetupConfig,
    list_prompts,
    load_global_vars,
    load_prompt_vars,
    load_vars_file,
    prompt_id_of,
)
from context_wizard.output import (
    OutputOptions,
    RichPromptDTO,
    resolve_delivery_directory,
    write_output,
)
from context_wizard.plugins import (
    AnswerDeliveryError,
    PluginContext,
    PluginRegistry,
    builtin_plugins_dir,
    discover_plugins,
)
from context_wizard.state import Source, VariableStore
from context_wizard.surveys import find_survey, load_survey, run_survey
from context_wizard.templating import render
from context_wizard.ui import WizardAborted, WizardUI

TOOLS_ENV_FILENAME = "tools.env"


@dataclass
class CollectorOptions:
    """Опции запуска конвейера."""

    output: OutputOptions
    prompt_id: str | None = None
    user_prompt: str | None = None
    invalidate: bool = False
    answer_target_ids: list[str] | None = None
    """Переопределение приёмников ответа по id (плагины должны быть установлены)."""


class Collector:
    """Собирает богатый промпт из артефактов проекта, взаимодействуя через :class:`WizardUI`."""

    def __init__(self, root: Path, config: SetupConfig, ui: WizardUI) -> None:
        self.root = root
        self.config = config
        self.ui = ui
        self.cache = Cache(root)
        self.store = VariableStore()
        self._registry: PluginRegistry | None = None

    def registry(self) -> PluginRegistry:
        """Реестр плагинов: глобальные/встроенные + проектные (проект переопределяет)."""
        if self._registry is None:
            project_plugin_dirs = [self.root / path for path in self.config.plugin_dirs]
            self._registry = discover_plugins(
                builtin_plugins_dir(),
                *project_plugin_dirs,
            )
        return self._registry

    def run(self, options: CollectorOptions) -> RichPromptDTO:
        """Пройти конвейер и вернуть готовый DTO."""
        if options.invalidate:
            self.cache.invalidate()

        self._load_global_vars()
        prompt_path = self._select_prompt(options.prompt_id)
        prompt_id = prompt_id_of(prompt_path)
        self._load_prompt_vars(prompt_id)

        template = prompt_path.read_text(encoding="utf-8")
        if options.user_prompt:
            template = f"{template}\n\n{options.user_prompt}"

        self._run_survey(prompt_id)

        targets = self._effective_targets(options)
        use_fs = all(target.use_fs for target in targets)

        if self._has_missing(template, use_fs):
            self._run_external_tool(use_fs)

        dto = self._render_final(template, use_fs)
        self._deliver(dto, options.output, use_fs, targets)
        return dto

    def _effective_targets(self, options: CollectorOptions) -> list[AnswerTargetConfig]:
        """Определить приёмники: конфигурация либо полное CLI-переопределение."""
        configured = self.config.answer_target_configs
        if options.answer_target_ids is None:
            return configured
        if len(options.answer_target_ids) != len(set(options.answer_target_ids)):
            raise ValueError("--answer-target не должен содержать повторяющиеся id")
        by_id = {target.id: target for target in configured}
        return [
            by_id.get(plugin_id, AnswerTargetConfig(id=plugin_id))
            for plugin_id in options.answer_target_ids
        ]

    # -- Шаги конвейера -------------------------------------------------

    def _load_global_vars(self) -> None:
        self.store.update(load_global_vars(self.root, self.config), Source.GLOBAL)

    def _select_prompt(self, prompt_id: str | None) -> Path:
        prompts = list_prompts(self.root)
        if not prompts:
            raise FileNotFoundError(f"В проекте нет промптов: {self.root / 'prompts'}")
        if prompt_id is not None:
            for path in prompts:
                if prompt_id_of(path) == prompt_id:
                    return path
            raise FileNotFoundError(f"Промпт не найден: {prompt_id!r}")
        return self.ui.select_prompt(prompts)

    def _load_prompt_vars(self, prompt_id: str) -> None:
        self.store.update(load_prompt_vars(self.root, prompt_id), Source.PROMPT_ENV)

    def _run_survey(self, prompt_id: str) -> None:
        survey_path = find_survey(self.root, prompt_id)
        if survey_path is None:
            return
        survey, warnings = load_survey(survey_path, self.root)
        for warning in warnings:
            self.ui.notify(warning)
        cache = self.cache.load_survey_answers(prompt_id)
        answers = run_survey(survey, self.ui, cache=cache)
        self.store.update(answers, Source.SURVEY)
        self.cache.save_survey_answers(prompt_id, cache)

    def _has_missing(self, template: str, use_fs: bool) -> bool:
        result = render(template, store=self.store, root=self.root, use_fs=use_fs)
        return bool(result.missing)

    def _run_external_tool(self, use_fs: bool) -> None:
        tool_id = self.config.external_tool
        if not tool_id:
            return
        registry = self.registry()
        if not registry.has_external(tool_id):
            self.ui.notify(f"Внешний инструмент {tool_id!r} не установлен — пропущен")
            return
        tool = registry.create_external(tool_id)
        tool_cache = self.cache.load_tool_cache(tool_id)
        context = PluginContext(
            root=self.root,
            store=self.store,
            ui=self.ui,
            use_fs=use_fs,
            settings=self.config.tool_settings,
            env=self._load_tools_env(),
            cache=tool_cache,
        )
        try:
            values = tool.run(context)
        except BaseException:
            # Авторизация и другие дорогие этапы могут уже обновить cache. Сохраняем их,
            # даже если пользователь отменил следующий выбор или загрузка завершилась ошибкой.
            with suppress(OSError, TypeError, ValueError):
                self.cache.save_tool_cache(tool_id, tool_cache)
            raise
        self.store.update(values, Source.EXTERNAL_TOOL)
        self.cache.save_tool_cache(tool_id, tool_cache)

    def _render_final(self, template: str, use_fs: bool) -> RichPromptDTO:
        result = render(template, store=self.store, root=self.root, use_fs=use_fs)
        if result.missing:
            skip = self.ui.resolve_missing(sorted(result.missing))
            result = render(
                template,
                store=self.store,
                root=self.root,
                use_fs=use_fs,
                skip=frozenset(skip),
            )
            for name in sorted(result.missing):
                self.ui.notify(f"Переменная {name!r} осталась пустой")
        return RichPromptDTO(
            prompt=result.text,
            attachments=result.attachments,
            root=self.root,
        )

    def _deliver(
        self,
        dto: RichPromptDTO,
        output: OutputOptions,
        use_fs: bool,
        targets: list[AnswerTargetConfig],
    ) -> None:
        if not targets:
            write_output(dto, output)
            return

        registry = self.registry()
        installed = [target for target in targets if registry.has_answer(target.id)]
        for target in targets:
            if not registry.has_answer(target.id):
                self.ui.notify(f"Приёмник {target.id!r} не установлен — пропущен")
        if not installed:
            write_output(dto, output)
            return

        delivery = resolve_delivery_directory(output, self.root)
        env = self._load_tools_env()
        notification_lock = Lock()

        def deliver(target: AnswerTargetConfig) -> None:
            context = PluginContext(
                root=self.root,
                store=self.store,
                ui=self.ui,
                use_fs=use_fs,
                settings=dict(target.settings),
                env=dict(env),
                output_dir=delivery.path,
                output_dir_ambiguous=delivery.ambiguous,
                notification_lock=notification_lock,
            )
            registry.create_answer(target.id).deliver(dto, context)

        failures: list[tuple[str, BaseException]] = []
        with ThreadPoolExecutor(max_workers=len(installed)) as executor:
            futures = [(target.id, executor.submit(deliver, target)) for target in installed]
            for plugin_id, future in futures:
                try:
                    future.result()
                except BaseException as error:
                    failures.append((plugin_id, error))
        if failures:
            raise AnswerDeliveryError(failures)

    def _load_tools_env(self) -> dict[str, str]:
        path = self.root / TOOLS_ENV_FILENAME
        if not path.is_file():
            return {}
        return {key: str(value) for key, value in load_vars_file(path).items()}


__all__ = ["Collector", "CollectorOptions", "WizardAborted"]
