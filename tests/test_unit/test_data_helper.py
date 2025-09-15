"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os


class TestDataHelper:
    @staticmethod
    def get_test_data_folder():
        return os.path.join(os.path.dirname(__file__), "test_data")

    @staticmethod
    def get_test_file(filename: str):
        return os.path.join(TestDataHelper.get_test_data_folder(), filename)
