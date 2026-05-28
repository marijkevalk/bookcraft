# book-formatter

> Format manuscript .docx files into a styled template

## Stack

- Python 3.12+, Click CLI
- Package manager: uv
- Linter/formatter: ruff
- Type checker: mypy (strict)
- Tests: pytest

## Commands

- `uv run pytest` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run mypy src/` — type check
- `uv run book-formatter` — run CLI

## Conventions

- Source code in `src/book_formatter/`
- Tests in `tests/`
- CLI uses Click groups and commands
