from atlas.math.timeseries import Timeseries


class ScenarioMatrix:
    """Stores Timeseries objects by scenario name, with access and deletion by name."""

    def __init__(self, name: str, indexes: list[str | int | float], timeseries: list[Timeseries]):
        """Initialize a ScenarioMatrix.

        :param name: The name of the matrix.
        :type name: str
        :param indexes: List of scenario names.
        :type indexes: list[str], optional
        :param timeseries: List of Timeseries corresponding to the scenario names.
        :type timeseries: list[Timeseries], optional
        :raises ValueError: If the number of indexes and timeseries do not match.
        """
        self.name: str | int | float = name

        self.scenarios: dict[str | int | float, Timeseries] = dict(
            zip(indexes, timeseries, strict=False),
        )

    def __len__(self) -> int:
        """Get the number of timeseries in the matrix.

        :return: Number of scenarios.
        :rtype: int
        """
        return len(self.scenarios)

    def __eq__(self, other: object) -> bool:
        """Check equality with another ScenarioMatrix.

        :param other: Another ScenarioMatrix instance.
        :type other: object
        :return: True if the matrices are equal, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, ScenarioMatrix):
            raise NotImplementedError(
                "Cannot compare ScenarioMatrix with non-ScenarioMatrix object",
            )

        return (
            self.name == other.name
            and list(self.scenarios.keys()) == list(other.scenarios.keys())
            and all(self.scenarios[k] == other.scenarios[k] for k in self.scenarios)
        )

    def __contains__(self, index: str | float) -> bool:
        """Check if a scenario exists in the matrix.

        :param index: Scenario name.
        :type index: str
        :return: True if the index exists, False otherwise.
        :rtype: bool
        """
        return index in self.scenarios

    def __getitem__(self, index: str | float) -> Timeseries:
        """Retrieve a timeseries by its scenario name.

        :param index: Scenario name.
        :type index: str or int
        :raises KeyError: If the index is not found.
        :return: The corresponding Timeseries.
        :rtype: Timeseries
        """
        if index not in self.scenarios:
            raise KeyError(f"No timeseries found for index: {index}")
        return self.scenarios[index]

    def add_timeseries(self, index: str | float, timeseries: Timeseries) -> None:
        """Add a timeseries to the matrix.

        :param index: Scenario name.
        :type index: str or int
        :param timeserie: Timeseries to add.
        :type timeserie: Timeseries
        :raises TypeError: If input types are invalid.
        """
        if not isinstance(index, str | int | float):
            raise TypeError(f"Expected index type str or numerical, got {type(index)}")
        if not isinstance(timeseries, Timeseries):
            raise TypeError(f"Expected timeserie type Timeseries, got {type(timeseries)}")

        self.scenarios[index] = timeseries

    def delete_timeseries(self, index: str) -> None:
        """Delete a timeseries from the matrix by scenario name.

        :param index: Scenario name.
        :type index: str
        :raises TypeError: If index is not a string.
        :raises KeyError: If the index does not exist.
        """
        if not isinstance(index, str | int | float):
            raise TypeError(f"Expected index type str, got {type(index)}")
        try:
            del self.scenarios[index]
        except KeyError:
            raise KeyError(f"No timeseries to delete at index: {index}")

    def get_timeseries(self, index: str | float) -> Timeseries:
        """Get a timeseries by scenario name.

        :param index: Scenario name.
        :type index: str or int
        :raises KeyError: If the index is not found.
        :return: Corresponding Timeseries.
        :rtype: Timeseries
        """
        return self.__getitem__(index)

    @property
    def indexes(self) -> list[str | int | float]:
        """List of scenario names.

        :return: List of scenario indexes.
        :rtype: list[str]
        """
        return list(self.scenarios.keys())
