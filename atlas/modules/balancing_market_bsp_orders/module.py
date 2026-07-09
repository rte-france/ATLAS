"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BSPBalancingOrdersModule.
"""

from atlas.abstract_class.module import AbstractModule
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_market_bsp_orders.input_dataset import BSPBalancingOrdersInputDataset
from atlas.modules.balancing_market_bsp_orders.order_formulators.hydro import HydraulicOrderFormulator
from atlas.modules.balancing_market_bsp_orders.order_formulators.load import LoadOrderFormulator
from atlas.modules.balancing_market_bsp_orders.order_formulators.storage import StorageOrderFormulator
from atlas.modules.balancing_market_bsp_orders.order_formulators.wind_solar import WindPvOrderFormulator
from atlas.modules.balancing_market_bsp_orders.output_dataset import BSPBalancingOrdersOutputDataset
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters


class BSPBalancingOrdersModule(
    AbstractModule[
        BSPBalancingOrdersParameters,
        BSPBalancingOrdersInputDataset,
        BSPBalancingOrdersOutputDataset,
    ]
):
    """Module that formulates balancing market orders for all eligible BSP equipments.

    The execute step iterates over all equipment types and delegates order formulation
    to the corresponding formulator in the order_formulators package.
    """

    def get_parameters_class(self) -> type[BSPBalancingOrdersParameters]:
        return BSPBalancingOrdersParameters

    def import_data(
        self,
        input_data: AtlasDataset,
        parameters: BSPBalancingOrdersParameters,
    ) -> BSPBalancingOrdersInputDataset:
        """Build the input dataset from the AtlasDataset and parameters.

        Filters equipments by market area, exclusion lists, technology,
        and maintenance status. Casts each equipment to its local balancing subclass.
        """
        return BSPBalancingOrdersInputDataset(
            input_data.set_frequency_all(parameters.temporal.timestep, inplace=True), parameters
        )

    def validate_data(
        self,
        parameters: BSPBalancingOrdersParameters,
        input_dataset: BSPBalancingOrdersInputDataset,
    ) -> bool:
        return True

    def execute(
        self,
        parameters: BSPBalancingOrdersParameters,
        input_dataset: BSPBalancingOrdersInputDataset,
    ) -> BSPBalancingOrdersOutputDataset:
        """Formulate balancing orders for all eligible equipments.

        Iterates over each technology group and delegates to the corresponding
        order formulator. Results are aggregated into the output dataset.
        """
        output_dataset = BSPBalancingOrdersOutputDataset()

        for load in input_dataset.load_equipments.values():
            orders, _ = LoadOrderFormulator(load, input_dataset.time_index, parameters).formulate()
            output_dataset.orders.extend(orders)

        for wind in input_dataset.wind_equipments.values():
            orders, _ = WindPvOrderFormulator(wind, input_dataset.time_index, parameters).formulate()
            output_dataset.orders.extend(orders)

        for solar in input_dataset.solar_equipments.values():
            orders, _ = WindPvOrderFormulator(solar, input_dataset.time_index, parameters).formulate()
            output_dataset.orders.extend(orders)

        for storage in input_dataset.storage_equipments.values():
            orders, _ = StorageOrderFormulator(storage, input_dataset.time_index, parameters).formulate()
            output_dataset.orders.extend(orders)

        for hydro in input_dataset.hydro_equipments.values():
            orders, _ = HydraulicOrderFormulator(hydro, input_dataset.time_index, parameters).formulate()
            output_dataset.orders.extend(orders)

        return output_dataset

    def validates_results(
        self,
        parameters: BSPBalancingOrdersParameters,
        input_dataset: BSPBalancingOrdersInputDataset,
        output_dataset: BSPBalancingOrdersOutputDataset,
    ) -> bool:
        return True

    def export_results(
        self,
        parameters: BSPBalancingOrdersParameters,
        input_dataset: BSPBalancingOrdersInputDataset,
        output_dataset: BSPBalancingOrdersOutputDataset,
    ) -> None:
        pass
