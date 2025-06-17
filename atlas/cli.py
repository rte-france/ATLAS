import typer

import atlas
from atlas.modules.portfolio_optimisation.main import _portfolio_optimisation

app = typer.Typer()


@app.command()
def portfolio_optimisation(
    parameters: str = typer.Option(help="Path to the yaml parameters file"),
    data: str = typer.Option(help="Path to the data directory"),
):
    """Run the portfolio optimisation"""
    _portfolio_optimisation(parameters=parameters, data=data)


@app.command()
def version() -> None:
    """Print the version of the package."""
    print(f"Atlas version : {atlas.__version__}")  # noqa: T201
