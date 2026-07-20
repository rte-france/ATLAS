"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""


class PriceGroup:
    def __init__(self, id: int, time_index: int):
        self.id = id
        self.time_index = time_index
        self.market_area_names: list[str] = []
        self.max_price = float("inf")
        self.min_price = -float("inf")
        self.min_rejected_sale = float("inf")
        self.max_rejected_buy = -float("inf")
