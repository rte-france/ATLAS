"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict


class BusinessModel(BaseModel):
    """Implements the business model of the ATLAS project."""

    name: str | None = None
    model_config = ConfigDict(arbitrary_types_allowed=True)
