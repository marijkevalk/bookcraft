# book-formatter

Format manuscript .docx files into a styled template

## Install

```bash
uv sync
```

## Usage

```bash
uv run book-formatter --help
uv run book-formatter hello
uv run book-formatter hello Opus
```

## Development

```bash
make test       # run tests
make lint       # check linting
make format     # auto-format
make typecheck  # run mypy
make all        # lint + typecheck + test
```

## Docker

```bash
docker build -t book-formatter .
docker run book-formatter hello
```
