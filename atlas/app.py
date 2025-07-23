import typer
from rich import print as rprint

import atlas

app = typer.Typer()


@app.command()
def version() -> None:
    """Print the version of the package."""
    rprint(f"[bold]Atlas version[/bold] : {atlas.__version__}")  # noqa: T201
