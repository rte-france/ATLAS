"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from atlas import BusinessModel
from atlas.enums import BusinessModelName
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container


class CurrentInputState:
    def __init__(self, data: AtlasDataset):
        self.data = data

    def to_directory(self, path: str | Path):
        """Write the current input state to a directory."""
        self.data.to_directory(path)

    def filter_dataset(
        self,
        included_types: Iterable[str | BusinessModelName] = (),
        filters: dict[str | BusinessModelName, Any] | None = None,
    ) -> AtlasDataset:
        return self.data.filter_dataset(included_types=included_types, filters=filters)
