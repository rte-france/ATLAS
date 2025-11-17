"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Callable, Any

from pydantic_extra_types.pendulum_dt import DateTime
import atlas.config as cfg


class ModelVarWrapper:
    """This class is used to add and manage values to an OptimisationModel variable outside its time limits."""

    def __init__(self, getter: Callable[[DateTime], Any], setter: Callable[[DateTime], Any]):
        # getter to get the value directly from the OptimisationModel object
        self._getter = getter
        # setter to set the value directly in the OptimisationModel object
        self._setter = setter
        # dictionary used to store values outside the time limits of the OptimisationModel time_frame
        self._extended_frame: dict[DateTime, int] = {}

    def get_value(self, t: DateTime) -> Any:
        """
        Get the value matching the DateTime key
        :param t: DateTime key
        :return: the value
        """
        if t in self._extended_frame.keys():
            return self._extended_frame[t]
        else:
            return self.get_model_var(t)

    def get_extended_value(self, t: DateTime) -> int:
        return self._extended_frame[t]

    def set_extended(self, t: DateTime, value: int):
        self._extended_frame[t] = value
        # check for duplicates
        try:
            var = self.get_model_var(t)
            cfg.logger.warning(f"the key {t} is a duplicates : it is also present in the model variable {var}")
        except ValueError:
            pass  # the DateTime key doesn't exist in the model, as intended

    def get_model_var(self, t: DateTime) -> Any:
        return self._getter(t)

    def set_model_var(self, t: DateTime):
        self._setter(t)
        # check for duplicates
        if t in self._extended_frame.keys():
            cfg.logger.warning(f"the key {t} is a duplicates : it is also present in the _extended_frame")
