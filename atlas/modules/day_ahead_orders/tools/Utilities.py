"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime


# Contains miscellaneous functions used in the various files.
class Utilities:
    @staticmethod
    def get_date_to_clean_string(date: DateTime) -> str:
        """Converts a datetime object to a string without special characters"""
        return date.format("YYYY_MM_DD_HH_mm_SS")
