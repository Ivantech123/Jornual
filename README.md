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

## Хранение данных

По умолчанию данные сохраняются в файл `data/journal.json`. Путь можно изменить через
переменную окружения `JOURNAL_PATH`.
