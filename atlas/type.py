"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime
from types import UnionType
from typing import TypedDict, get_args, get_origin

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import BusinessModelName
from atlas.io_utils.utils import to_snake_case
from atlas.objects.business_model import BusinessModel


class TimeseriesDict(TypedDict):
    time: list[datetime] | list[DateTime]
    value: list[float] | list[int]


def get_type_attribute(
    object_type: BusinessModelName, attribute: str
) -> type[BusinessModel] | str | int | float | None:
    """Get type of attribute for a given object type."""
    if object_type not in cfg.MODEL_MAPPING_NAME:
        raise ValueError(f"Object type {object_type} is not valid.")

    if attribute not in cfg.MODEL_MAPPING_NAME[object_type].model_fields:
        cfg.logger.debug(f"The attribute '{attribute}' is not present in Atlas model object : {object_type}")
        return None
    attribute_type = cfg.MODEL_MAPPING_NAME[object_type].model_fields[attribute].annotation

    if get_origin(attribute_type) is UnionType:
        model = get_args(attribute_type)[0]
        if model is None:
            model = get_args(attribute_type)[1]
    else:
        model = attribute_type
    return model


def get_class_inheritance_chain(
    class_name: BusinessModelName, as_pydantic: bool = False
) -> list[str] | list[type[BusinessModel]]:
    """
    Given the name of a class and a mapping from names to class objects,
    return the class inheritance chain as a list of class names (as strings),
    from the class itself up to `object`.

    """
    cls = cfg.MODEL_MAPPING_NAME.get(class_name)
    if cls is None:
        raise ValueError(f"Class '{class_name}' not found in model_mapping.")

    mro_chain = cls.mro()
    return mro_chain if as_pydantic else [to_snake_case(base.__name__) for base in mro_chain]  # type: ignore[misc]
