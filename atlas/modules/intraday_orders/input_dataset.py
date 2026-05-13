"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import AtlasDataset, Hydro, Load, OtherNonDispatchable, Solar, Storage, Thermal, Wind
from atlas.abstract_class.dataset import AbstractDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


class IntradayOrdersInputDataset(AbstractDataset[IntradayOrdersParameters]):
    def __init__(self, input_dataset: AtlasDataset):
        self.hydro: list[Hydro] = input_dataset.hydro.all()
        self.load: list[Load] = input_dataset.load.all()
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_dataset.other_non_dispatchable.all()
        self.solar: list[Solar] = input_dataset.solar.all()
        self.storage: list[Storage] = input_dataset.storage.all()
        self.thermal: list[Thermal] = input_dataset.thermal.all()
        self.wind: list[Wind] = input_dataset.wind.all()
