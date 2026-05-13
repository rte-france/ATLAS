"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

import atlas.config as cfg
from atlas import AtlasDataset, Equipment, Hydro, Load, OtherNonDispatchable, Solar, Storage, Thermal, Wind
from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.container import Container
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters

T = TypeVar("T", bound=Equipment)


def container_to_list(container: Container[T]) -> list[T]:
    data_list = []
    for item in container:
        data_list.append(item)
    return data_list


def has_hydro_water_values(hydro: Hydro) -> bool:
    if len(hydro.storage_marginal_value.index) == 0:
        msg = f"There are no water values for instance {hydro.name}. This instance will be ignored in the calculation."
        cfg.logger.warning(msg)
        return False
    return True


class IntradayOrdersInputDataset(AbstractDataset[IntradayOrdersParameters]):
    def __init__(self, input_dataset: AtlasDataset):
        self.__hydro: list[Hydro] = list(filter(has_hydro_water_values, container_to_list(input_dataset.hydro)))
        self.__load: list[Load] = container_to_list(input_dataset.load)
        self.__other_non_dispatchable: list[OtherNonDispatchable] = container_to_list(
            input_dataset.other_non_dispatchable
        )
        self.__solar: list[Solar] = container_to_list(input_dataset.solar)
        self.__storage: list[Storage] = container_to_list(input_dataset.storage)
        self.__thermal: list[Thermal] = container_to_list(input_dataset.thermal)
        self.__wind: list[Wind] = container_to_list(input_dataset.wind)

    @property
    def hydro(self) -> list[Hydro]:
        return self.__hydro[:]

    @property
    def load(self) -> list[Load]:
        return self.__load[:]

    @property
    def other_non_dispatchable(self) -> list[OtherNonDispatchable]:
        return self.__other_non_dispatchable[:]

    @property
    def solar(self) -> list[Solar]:
        return self.__solar[:]

    @property
    def storage(self) -> list[Storage]:
        return self.__storage[:]

    @property
    def thermal(self) -> list[Thermal]:
        return self.__thermal[:]

    @property
    def wind(self) -> list[Wind]:
        return self.__wind[:]
