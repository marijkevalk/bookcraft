"""book-formatter CLI."""

import click

from book_formatter import __version__


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """Format manuscript .docx files into a styled template"""


@cli.command()
@click.argument("name", default="world")
def hello(name: str) -> None:
    """Say hello."""
    click.echo(f"Hello, {name}!")


if __name__ == "__main__":
    cli()
