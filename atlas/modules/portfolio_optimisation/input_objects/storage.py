"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
from atlas.enums import StorageType


class StoragePO(StorageDispatchInput):
    storage_type: StorageType
    maximum_fcr: float
    maximum_afrr: float
