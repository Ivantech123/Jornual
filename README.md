# Журнал преподавателя (CLI)

Консольный журнал для учителя на Python: хранит список учеников, оценки и посещаемость
в JSON-файле и позволяет получать сводку и отчеты по каждому ученику.

## Возможности

- Добавление учеников.
- Выставление оценок по предметам.
- Отметка посещаемости (присутствовал/отсутствовал) с датами.
- Сводная статистика по классу.
- Индивидуальный отчет по ученику.

## Требования

- Python 3.8+
- Внешние зависимости не требуются (`requirements.txt` пустой).

## Быстрый старт

```bash
python journal.py add-student --student-id S001 --name "Иван Петров"
python journal.py add-grade --student-id S001 --subject "Математика" --grade 5
python journal.py mark-attendance --student-id S001 --date 2024-09-01 --present
python journal.py summary
python journal.py show-student --student-id S001 --with-notes
```

## Веб-интерфейс

Запустите встроенный веб-сервер и откройте браузер:

```bash
python journal.py serve --host 0.0.0.0 --port 8000
```

Интерфейс доступен по адресу `http://localhost:8000`.

## Хранение данных

По умолчанию данные сохраняются в файл `journal.json`. Путь можно изменить через флаг
`--storage`.
