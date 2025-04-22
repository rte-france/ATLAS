from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries


class ScenarioMatrix(Matrix[str | int | float]):
    """Stores Timeseries objects by scenario name, with access and deletion by name."""

    def __init__(self, name: str, indexes: list[str | int | float], timeseries: list[Timeseries]):
        super().__init__(name, indexes, timeseries)
