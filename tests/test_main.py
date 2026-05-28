"""Tests for book-formatter CLI."""

from click.testing import CliRunner

from book_formatter.main import cli


def test_version():
    """CLI shows version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_hello_default():
    """Hello command with default name."""
    runner = CliRunner()
    result = runner.invoke(cli, ["hello"])
    assert result.exit_code == 0
    assert "Hello, world!" in result.output


def test_hello_custom():
    """Hello command with custom name."""
    runner = CliRunner()
    result = runner.invoke(cli, ["hello", "Opus"])
    assert result.exit_code == 0
    assert "Hello, Opus!" in result.output
