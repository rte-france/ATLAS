"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import List, TypeVar

import atlas.config as cfg
from atlas import AtlasDataset, Wind, Solar, Thermal, OtherNonDispatchable, Hydro, Load, Storage, Equipment
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.io_utils.container import Container
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters

T = TypeVar("T", bound=Equipment)


def container_to_list(container: Container[T]) -> List[T]:
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
    def __init__(self, raw_data: AtlasDataset):
        self.__hydro: List[Hydro] = list(filter(has_hydro_water_values, container_to_list(raw_data.hydro)))
        self.__load: List[Load] = container_to_list(raw_data.load)
        self.__other_non_dispatchable: List[OtherNonDispatchable] = container_to_list(raw_data.other_non_dispatchable)
        self.__solar: List[Solar] = container_to_list(raw_data.solar)
        self.__storage: List[Storage] = container_to_list(raw_data.storage)
        self.__thermal: List[Thermal] = container_to_list(raw_data.thermal)
        self.__wind: List[Wind] = container_to_list(raw_data.wind)

    @property
    def hydro(self) -> List[Hydro]:
        return self.__hydro[:]

    @property
    def load(self) -> List[Load]:
        return self.__load[:]

    @property
    def other_non_dispatchable(self) -> List[OtherNonDispatchable]:
        return self.__other_non_dispatchable[:]

    @property
    def solar(self) -> List[Solar]:
        return self.__solar[:]

    @property
    def storage(self) -> List[Storage]:
        return self.__storage[:]

    @property
    def thermal(self) -> List[Thermal]:
        return self.__thermal[:]

    @property
    def wind(self) -> List[Wind]:
        return self.__wind[:]
