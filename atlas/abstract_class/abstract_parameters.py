"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""

from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from atlas.constants import DATE_FORMAT


class AbstractParameters(BaseModel):
    """Base class for parameters, to be extended by concrete implementations.

    :param start_date: Study start date
    :type start_date: datetime
    :param end_date: Study end date
    :type end_date: datetime
    :param execution_date: Study execution date
    :type execution_date: datetime
    :param export_result: true if result should be export else false
    :type export_result: bool
    :param export_output_dataset: true if business model object output should be export else false
    :type export_output_dataset: bool
    """

    start_date: datetime | None = None
    end_date: datetime | None = None
    execution_date: datetime | None = None
    export_result: bool | None = True
    export_output_dataset: bool | None = False

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        """Validation of start, end and execution date

        :raises ValueError: If the start, end and execution date are not coherent
        :return: The AbstractParameters if dates are validate
        :rtype: AbstractParameters
        """
        if self.end_date is None or self.start_date is None:
            return self
        if self.end_date < self.start_date:
            raise ValueError(
                f"Start date '{self.start_date.strftime(DATE_FORMAT)}' must be inferior "
                f"to end date '{self.end_date.strftime(DATE_FORMAT)}'"
            )
        if self.execution_date is None:
            return self
        if not (self.start_date < self.execution_date < self.end_date):
            raise ValueError(
                f"Execution date '{self.execution_date.strftime(DATE_FORMAT)}' must be between "
                f"start date '{self.start_date.strftime(DATE_FORMAT)}' and "
                f"end date '{self.end_date.strftime(DATE_FORMAT)}'"
            )
        return self


module_parameters_type_var = TypeVar("module_parameters_type_var", bound=AbstractParameters)
