"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ScenarioMatrix
"""

from atlas.math.timeseries import Timeseries


class ScenarioMatrix:
    """A class that stores Timeseries by scenario names and allows to access and delete
    them by their name.
    """

    def __init__(self, name, indexes=None, timeseries=None):
        """Create a ScenarioMatrix from a list of timeseries

        :param name: str. Name of the matrix
        :param indexes: list of str. Name of each scenario of the matrix
        :param timeseries: list of Timeseries. Timeseries of each scenario of the matrix
        """
        if indexes is None:
            indexes = []
        if timeseries is None:
            timeseries = []

        if len(indexes) != len(timeseries):
            raise ValueError(
                "names and timeseries parameters must contain the same number of elements",
            )

        self.name = name
        self.indexes = indexes
        self.scenarios = dict(zip(indexes, timeseries, strict=False))

    def __len__(self):
        return len(self.scenarios)

    def __eq__(self, other_matrix):
        """Test whether two ScenarioMatrix objects are equal.
        Objects are considered equal if they store the same name, scenarios names/timeseries.

        :param other_matrix: ScenarioMatrix. The other forecasting matrix to compare to.
        :return: True if equal else False.
        """
        if self.name != other_matrix.name:
            return False
        if self.indexes != other_matrix.indexes:
            return False
        if self.scenarios.keys() != other_matrix.scenarios.keys():
            return False
        for name, timeserie in self.scenarios.items():
            if timeserie != other_matrix.scenarios[name]:
                return False
        return True

    def add_timeseries(self, index, timeserie):
        """Add a timeserie at the given index in the matrix

        :param index: str or int. The index to set the timeseries in the matrix
        :param timeserie: Timeseries. The timeserie to add in the matrix
        :return: Timeseries
        """
        if not isinstance(index, (str, int)):
            raise TypeError(f"Expected index type str or int, got {type(index)}")

        if not isinstance(timeserie, Timeseries):
            raise TypeError(f"Expected timeserie type Timeseries, got {type(index)}")

        self.indexes.append(index)
        self.scenarios[index] = timeserie

    def delete_timeseries(self, index):
        """Delete timeserie at the given index in the matrix

        :param index: str. The index of the timeserie to delete in the matrix
        :return:
        """
        if not isinstance(index, str):
            raise TypeError(f"Expected index type str, got {type(index)}")

        if index in self.scenarios:
            # Delete value in scenarios dict
            del self.scenarios[index]
            # Find its index in indexes list and delete it
            ind = self.indexes.index(index)
            del self.indexes[ind]

    def get_timeseries(self, index):
        """Returns the Timeseries for the given index

        :param index: str or int. The index of the timeseries to get in the matrix
        :return: Timeseries
        """
        # TODO Maybe raise error if index not in self.scenarios
        if index in self.scenarios:
            return self.scenarios[index]

    def __getitem__(self, index):
        return self.get_timeseries(index)
