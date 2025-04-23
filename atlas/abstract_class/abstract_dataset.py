"""
Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractModule
"""

from pydantic import BaseModel


class AbstractParameters(BaseModel):
    """Base class for parameters, to be extended by concrete implementations."""
