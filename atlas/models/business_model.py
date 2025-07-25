"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict


class BusinessModel(BaseModel):
    """Implements the Atlas business models."""

    name: str
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name})"

    def __str__(self):
        return f"{self.__class__.__name__}(name={self.name})"
