"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.io_utils.atlas_dataset import AtlasDataset


class CurrentInputState:
    def __init__(self, data: AtlasDataset):
        self.data = data
