"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""

from datetime import datetime
from typing import Annotated, TypeVar

import pendulum
from pendulum import DateTime
from pydantic import BaseModel, BeforeValidator, model_validator
from pydantic_extra_types.pendulum_dt import DateTime
from typing_extensions import Self

from atlas.config import logger


def to_pendulum_date(date: str | DateTime | datetime | None) -> DateTime | None:
    date_format = "DD/MM/YYYY HH:mm:ss"
    if isinstance(date, str):
        try:
            return pendulum.from_format(date, date_format)
        except ValueError:
            logger.exception(f"{date} doesn't not match {date_format}")
            # ValueError is not catch
            pendulum_date = pendulum.parse(date)
            if isinstance(pendulum_date, DateTime):
                return pendulum_date
            else:
                logger.exception(f"{date} doesn't not match {date_format}")
    elif isinstance(date, datetime):
        return pendulum.instance(date)
    elif isinstance(date, DateTime):
        return date
    return None


datetime_type = Annotated[DateTime, BeforeValidator(to_pendulum_date)]


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

    start_date: datetime_type | None = None
    end_date: datetime_type | None = None
    execution_date: datetime_type | None = None
    export_result: bool = True
    export_output_dataset: bool = False

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
                f"Start date '{self.start_date.to_datetime_string()}' must be inferior "
                f"to end date '{self.end_date.to_datetime_string()}'"
            )
        return self


module_parameters_type_var = TypeVar("module_parameters_type_var", bound=AbstractParameters)
