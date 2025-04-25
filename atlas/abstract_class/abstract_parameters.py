"""
Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""
from datetime import datetime

from pydantic import BaseModel, model_validator

from atlas.constants import DATE_FORMAT


class AbstractParameters(BaseModel):
    """Base class for parameters, to be extended by concrete implementations.

    :param start_date: Study start date
    :type start_date: datetime
    :param end_date: Study end date
    :type end_date: datetime
    :param execution_date: Study execution date
    :type execution_date: datetime
    """
    start_date: datetime | None = None
    end_date: datetime | None = None
    execution_date: datetime | None = None

    @model_validator(mode='after')
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError(f"Start date '{self.start_date.strftime(DATE_FORMAT)}' must be inferior "
                             f"to end date '{self.end_date.strftime(DATE_FORMAT)}'")
        if not (self.start_date < self.execution_date < self.end_date):
            raise ValueError(f"Execution date '{self.execution_date.strftime(DATE_FORMAT)}' must be between "
                             f"start date '{self.start_date.strftime(DATE_FORMAT)}' and "
                             f"end date '{self.end_date.strftime(DATE_FORMAT)}'")
        return self
