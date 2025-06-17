import typer

import atlas

app = typer.Typer()


@app.command()
def version() -> None:
    """Print the version of the package."""
    print(f"Atlas version : {atlas.__version__}")  # noqa: T201
