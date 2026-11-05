"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Every LP name is built from the timestep's :class:`pendulum.DateTime` rather than its position in
``input_dataset.times``: a name is then self-describing and stays stable whatever the simulation
window, and the module never has to convert an index back into a datetime. The datetime is
interpolated as-is; the OR-Tools exporter turns its separators into underscores, so
``2028-09-27 13:00:00+00:00`` reads as ``2028_09_27_13_00_00_00_00`` in the exported LP.

Names are built where their variable or constraint is created; only the names read back elsewhere
live here. Abbreviations used in the LP names:

- lo: linked orders (an IDENTICAL_VOLUME/IDENTICAL_RATIO/COMPLEMENT/circular-PC group)
- pc: parent-child (an order coupling of type PARENT_CHILDREN)
- idv / idr: identical volume / identical ratio (order coupling types)
- compl: complement (the COMPLEMENT order coupling type)
- qo: quantity of an order (its accepted power)
- rej: rejected
- mkt: market
- o_n / g_n: order name / (order coupling) group name
- xsis / nus: xi / nu, the auxiliary variables from the loss-factor formulation in the spec
"""

import pendulum


def critical_branch_constraint_name(branch_name: str, time: pendulum.DateTime) -> str:
    """Flow limit of a critical branch (3.6.2), whose slack tells the pricing which branches are saturated."""
    return f"Constraint_3_6_2_t_{time}_cb_{branch_name}"


def exchange_across_border_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    """Tie of a border exchange to the start of its resolution block (3.7)."""
    return f"Constraint_3_7_t_{time}_mkt_border_{border_name}"


def delta_p_pc(index_pc: int) -> str:
    """Paradoxical delta-P of a parent-child group, in the third pricing attempt."""
    return f"delta_p_PC_{index_pc}"
