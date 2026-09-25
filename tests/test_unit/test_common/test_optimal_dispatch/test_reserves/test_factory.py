"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.common.optimal_dispatch.reserves.factory import ReserveFactory
from atlas.common.optimal_dispatch.reserves.hydro import HydroReserveHandler
from atlas.common.optimal_dispatch.reserves.renewable import RenewableReserveHandler
from atlas.common.optimal_dispatch.reserves.storage import StorageReserveHandler
from atlas.common.optimal_dispatch.reserves.thermal import ThermalReserveHandler
from atlas.enums import StorageType
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.storage import Storage
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.equipment.wind import Wind

DISPATCH = object()
"""The factory only forwards the dispatch component — it is never dereferenced here."""


def _thermal(node, portfolio, **kwargs):
    return Thermal(name="th", node=node, portfolio=portfolio, **kwargs)


def _storage(node, portfolio, **kwargs):
    return Storage(name="st", node=node, portfolio=portfolio, storage_type=StorageType.BATTERY, **kwargs)


def _wind(node, portfolio, **kwargs):
    return Wind(name="wi", node=node, portfolio=portfolio, **kwargs)


def _hydro(node, portfolio, **kwargs):
    return Hydro(name="hy", node=node, portfolio=portfolio, **kwargs)


class TestReserveFactoryHandlerType:
    def test_for_thermal_returns_thermal_handler(self, node, portfolio):
        handler = ReserveFactory.for_thermal(_thermal(node, portfolio), DISPATCH)
        assert isinstance(handler, ThermalReserveHandler)

    def test_for_storage_returns_storage_handler(self, node, portfolio):
        handler = ReserveFactory.for_storage(_storage(node, portfolio))
        assert isinstance(handler, StorageReserveHandler)

    def test_for_renewable_returns_renewable_handler(self, node, portfolio):
        handler = ReserveFactory.for_renewable(_wind(node, portfolio))
        assert isinstance(handler, RenewableReserveHandler)

    def test_for_hydro_returns_hydro_handler(self, node, portfolio):
        handler = ReserveFactory.for_hydro(_hydro(node, portfolio), DISPATCH)
        assert isinstance(handler, HydroReserveHandler)


class TestReserveFactoryMaximumAutomated:
    """``maximum_automated`` drives every automated-reserve bound — pin the arithmetic."""

    def test_thermal_sums_afrr_and_fcr(self, node, portfolio):
        handler = ReserveFactory.for_thermal(_thermal(node, portfolio, maximum_afrr=30.0, maximum_fcr=12.5), DISPATCH)
        assert handler._maximum_automated == pytest.approx(42.5)

    def test_storage_sums_afrr_and_fcr(self, node, portfolio):
        handler = ReserveFactory.for_storage(_storage(node, portfolio, maximum_afrr=30.0, maximum_fcr=12.5))
        assert handler._maximum_automated == pytest.approx(42.5)

    def test_renewable_sums_afrr_and_fcr(self, node, portfolio):
        handler = ReserveFactory.for_renewable(_wind(node, portfolio, maximum_afrr=30.0, maximum_fcr=12.5))
        assert handler._maximum_automated == pytest.approx(42.5)

    def test_hydro_sums_afrr_and_fcr(self, node, portfolio):
        handler = ReserveFactory.for_hydro(_hydro(node, portfolio, maximum_afrr=30.0, maximum_fcr=12.5), DISPATCH)
        assert handler._maximum_automated == pytest.approx(42.5)

    @pytest.mark.parametrize(
        ("afrr", "fcr", "expected"),
        [
            (None, None, 0.0),
            (30.0, None, 30.0),
            (None, 12.5, 12.5),
        ],
    )
    def test_unset_capacities_count_as_zero(self, node, portfolio, afrr, fcr, expected):
        """Both fields are optional on Equipment — an unset one must not poison the sum."""
        handler = ReserveFactory.for_thermal(
            _thermal(node, portfolio, maximum_afrr=afrr, maximum_fcr=fcr), DISPATCH
        )
        assert handler._maximum_automated == pytest.approx(expected)


class TestReserveFactoryWiring:
    def test_name_is_propagated(self, node, portfolio):
        handler = ReserveFactory.for_storage(_storage(node, portfolio))
        assert handler.var("reserves_up", "T") == "reserves_up_st_T"

    def test_dispatch_is_forwarded(self, node, portfolio):
        handler = ReserveFactory.for_thermal(_thermal(node, portfolio), DISPATCH)
        assert handler._dispatch is DISPATCH
