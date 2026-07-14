# Moodle example

Экспериментальный проектный плагин получает последнюю доступную работу студента из
Moodle `mod_assign` или `mod_poasassignment` без web services/XML API. Для POAS в
контекст также добавляется индивидуальный вариант задания.

## Настройка

1. Скопируйте `moodle.sites.example.json` как `moodle.sites.json`.
2. Заполните в локальном JSON список Moodle-сайтов. Для каждого сайта задаются `id`, `name`,
   `url`, а также имена credential-переменных `username_env` и `password_env`.
3. Скопируйте `tools.env.example` как `tools.env` и заполните переменные, указанные в JSON,
   либо оставьте их пустыми для запроса credentials в TUI.

`moodle.sites.json` и `tools.env` игнорируются Git. `setup.toml` содержит только подключение
плагина и не раскрывает список или адреса Moodle-сайтов.

Пример запуска:

```powershell
uv run context-wizard examples/moodle --prompt review --output out
```

Cookies сохраняются в `examples/moodle/.tmp/tools/moodle.json` и разделяются по site id и
origin. Пароли туда не записываются. `--invalidate` удаляет cookies и загруженные работы.

По умолчанию разрешены только HTTPS URL. Для локального тестового Moodle по HTTP можно
явно добавить `"allow_http": true` в соответствующий объект сайта в `moodle.sites.json`.

После выбора студента плагин скачивает файлы его актуальной попытки в отдельный каталог
`examples/moodle/.tmp/moodle/downloads/`; в итоговый контекст передаётся локальный файл
или каталог, а не URL Moodle.

Плагин выполняет только вход, чтение HTML и скачивание выбранной работы. Он не переходит
по ссылкам действий и не изменяет оценки, feedback, статус отправки или содержимое курса.
