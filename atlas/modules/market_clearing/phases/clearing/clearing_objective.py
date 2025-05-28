"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

class ClearingObjective:
    def __init__(self):
        self.objective = None
        self.accepted_powers = None
        self.global_exchanges = None
        self.max_exchanges = None
        self.min_exchanges = None

    def build(self):
        """ Create objective function for the clearing phase model"""