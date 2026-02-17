"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""

from typing import TypeVar

from pydantic import ConfigDict, model_validator
from pydantic_extra_types.pendulum_dt import DateTime
from typing_extensions import Self

from atlas.enums import SolverEnum
from atlas.io_utils.parameters import Parameters


class AbstractParameters(Parameters):
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
    :param solver_name: Name of the solver to use
    :type solver_name: SolverEnum
    """

    start_date: DateTime
    end_date: DateTime
    execution_date: DateTime
    export_result: bool = True
    export_output_dataset: bool = False
    solver_name: SolverEnum = SolverEnum.XPRESS

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        """Validation of start, end and execution date

        :raises ValueError: If the start, end and execution date are not coherent
        :return: The AbstractParameters if dates are validate
        :rtype: AbstractParameters
        """
        if self.end_date < self.start_date:
            raise ValueError(
                f"Start date '{self.start_date.to_datetime_string()}' must be previous "
                f"to end date '{self.end_date.to_datetime_string()}'"
            )
        return self


module_parameters_type_var = TypeVar("module_parameters_type_var", bound=AbstractParameters)
