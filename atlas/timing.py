"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import functools
import time

from atlas import logger


def timeit(func):  # noqa: ANN001, ANN201
    """Decorator to measure the execution time for a method."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        start_time = time.perf_counter()
        result = func(self, *args, **kwargs)
        end_time = time.perf_counter()
        logger.debug(f"{self.__class__.__name__}.{func.__name__} executed in {end_time - start_time:.6f} seconds")
        return result

    return wrapper
