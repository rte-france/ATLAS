"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
from collections.abc import Iterable
from typing import Any

from atlas import BusinessModel
from atlas.enums import BusinessModelName
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container


class CurrentInputState:
    def __init__(self, data: AtlasDataset):
        self.data = data

    def filter_dataset(
        self,
        included_types: Iterable[str | BusinessModelName] = (),
        filters: dict[str | BusinessModelName, Any] | None = None,
    ) -> AtlasDataset:
        filtered_data: dict[str, list[BusinessModel]] = {}
        dataset_copy = copy.deepcopy(self.data)
        for object_type in included_types:
            object_type_str = object_type.value if isinstance(object_type, BusinessModelName) else object_type
            if not filters or object_type_str not in filters:
                try:
                    container: Container[BusinessModel] = dataset_copy.get_container_by_type(object_type_str)
                    filtered_data[object_type_str] = list(container)
                except ValueError:
                    # skip unknown types
                    continue

        # Apply filters
        if filters:
            for object_type, filter_fn in filters.items():
                object_type_str = object_type.value if isinstance(object_type, BusinessModelName) else object_type
                try:
                    filtered_container: Container[BusinessModel] = dataset_copy.get_container_by_type(object_type_str)
                    filtered_data[object_type_str] = [obj for obj in filtered_container if filter_fn(obj)]
                except ValueError:
                    continue

        return AtlasDataset.from_dict(filtered_data)
