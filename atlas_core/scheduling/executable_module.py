"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC, abstractmethod

class ExecutableModule(ABC):
    @abstractmethod
    def execute(self, parameters, input_marker):
        pass