"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""

from pathlib import Path
from typing import TypeVar

from atlas.io_utils.parameters import Parameters


class AbstractParameters(Parameters):
    """Base class for parameters, to be extended by concrete implementations.

    :param relative_src: Source for the relative path
    :type relative_src: Path
    """

    relative_src: Path = Path()

    def get_path(cls, relative_path):
        return cls.relative_src / relative_path


P = TypeVar("P", bound=AbstractParameters)
