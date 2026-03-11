"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""
from pathlib import Path

from pendulum import Duration
from pydantic import ConfigDict, model_validator, BaseModel, Field
from pydantic_extra_types.pendulum_dt import DateTime
from typing_extensions import Self

from atlas.enums import SolverEnum


class DateParameters(BaseModel):
    start_date: DateTime
    end_date: DateTime
    execution_date: DateTime

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


class SolverParameters(BaseModel):
    solver_name: SolverEnum = SolverEnum.XPRESS
    export_lp: bool = False
    use_presolve: bool = False
    solver_duality_gap: float = Field(0.0001, description="duality gap used for the optimization.")
    solver_timeout: Duration = Field(
        default_factory=lambda: Duration(minutes=4), description="Timeout of the optimization."
    )
    model_config = ConfigDict(arbitrary_types_allowed=True)

class MultiProcessingParameters(BaseModel):
    use_multiprocessing: bool = False
    max_workers: int | None = None


class OutputParameters(BaseModel):
    export_result: bool = False
    export_output_dataset: bool = False
    output_dir: Path = Path()
