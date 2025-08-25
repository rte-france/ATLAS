"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters

##### Etat des lieux au 16.10.2020 ####
#
# Base, semi base terminés
# Semi base : approfondir les tests, mais la formulation d'ordres et la formation des fenêtres
# temporelles a été testée et fonctionne.
# Les fonctions qui génèrent les états pour la semi base et celle qui crée les ordres d'exclusion semblent
# fonctionner correctement aussi.
#
# Sur le fonctionnement :
#
# startup cost : calculé dans retrieve_online_sequences, du coup détecté uniquement sur le bloc courant
# et amorti sur celui ci.
# liens d'exclusion entre les scénarios : définis entre les blocs inflexibles, donc seulement définis si la p_min est positive
# sur au moins un pas de temps.
#
# Pointe à faire

# FC: New improved structure of this file for clarity, organized as follows:
# . Main function, calling order formulation functions for each strategy
# . Orders formulation per strategy
# . Function formulating orders for each individual units (used for Baseload and Intermediate strategies)
# . Functions used to identify unique cases amongst High, Low and Medium Priceforecasts scenarios
# . Functions used to extract sequences and states


class ThermicBidding:
    # ------ Main function ------
    @staticmethod
    def formulate_thermic_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        """
        This wrapper function formulates orders for all thermic units.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.

        Returns None
        """

        # Formulate baseload orders
        cfg.logger.info("Formulation of the thermic baseload orders...")
        # ThermicBiding.formulate_thermic_baseload_orders(dataset, orders_time, parameters)

        # Formulate intermediate load orders
        cfg.logger.info(
            "Baseload orders formulation completed. Moving on to the formulation of the intermediate load orders..."
        )
        # ThermicBiding.formulate_thermic_intermediate_load_orders(dataset, orders_time, parameters)

        # Formulate peak load orders
        cfg.logger.info(
            "Intermediate load orders formulation completed. Moving on to the formulation of the peak load orders..."
        )
        # ThermicBiding.formulate_thermic_peak_load_orders(dataset, orders_time, parameters)
        cfg.logger.info("Peak load orders formulation completed.")

        # This is done last and not during the bidding process because of mutually exclusive programs, and to simplify debug
        cfg.logger.info("Computing maximum sell volumes...")
        # ThermicBiding.computeDASellSubmittedVolumes(dataset, orders_time)
        cfg.logger.info("End of computation.")

        return None
