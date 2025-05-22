"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from types import UnionType
from typing import get_args, get_origin

import atlas.config as cfg
from atlas.models.business_model import BusinessModel


def get_type_attribute(object_type: str, attribute: str) -> type[BusinessModel] | str | int | float | None:
    """Get type of attribute for a given object type."""
    if object_type not in cfg.MODEL_MAPPING_NAME:
        raise ValueError(f"Object type {object_type} is not valid.")

    if attribute not in cfg.MODEL_MAPPING_NAME[object_type].model_fields:
        raise KeyError(f"The attribute {attribute} is not present in Atlas model object : {object_type}")
    attribute_type = cfg.MODEL_MAPPING_NAME[object_type].model_fields[attribute].annotation

    if get_origin(attribute_type) is UnionType:
        model = get_args(attribute_type)[0]
        if model is None:
            model = get_args(attribute_type)[1]
    else:
        model = attribute_type
    return model
