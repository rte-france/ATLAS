"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import numpy as np
from antares.craft import Frequency, MCIndAreasDataType, MCIndLinksDataType
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import LoadType, StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_cluster_weights_from_bc
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.storage import Storage


def convert_electric_vehicle_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Electric Vehicle technologies from Antares to Atlas Storage equipment.

    EV units are modeled as Storage equipment with V2G capabilities:
    - Standard EVs for most areas
    - Special handling for France with two EV types (night-only and regular)
    - France also includes heavy vehicles as Load equipment

    Requires displacement energy and node-specific parameters from CSV files.
    """
    logger.info("Converting Electric Vehicle units")

    baseline_displacement_energy_ts = _load_baseline_displacement_energy(parameters)
    specific_node_parameters = _load_specific_node_parameters(parameters)

    ev_units = _convert_standard_evs(
        study=study,
        parameters=parameters,
        atlas_dataset=atlas_dataset,
        baseline_displacement_energy_ts=baseline_displacement_energy_ts,
        specific_node_parameters=specific_node_parameters,
    )

    if "fr" in parameters.market_areas:
        ev_units += _convert_france_evs(
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            baseline_displacement_energy_ts=baseline_displacement_energy_ts,
            specific_node_parameters=specific_node_parameters,
        )

        hv_units = _convert_france_heavy_vehicles(
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
        )
        atlas_dataset.load.add(hv_units)

    atlas_dataset.storage.add(ev_units)

    return atlas_dataset


def _load_baseline_displacement_energy(parameters: AntaresToAtlasParameters) -> Timeseries | None:
    """Load baseline displacement energy from CSV file (first column, semicolon-separated, header skipped)."""
    if parameters.baseline_displacement_energy is None:
        logger.warning("baseline_displacement_energy parameter not set, skipping EV displacement energy")
        return None

    file_path = Path(parameters.baseline_displacement_energy)
    if not file_path.exists():
        logger.warning(f"Baseline displacement energy file not found: {file_path}")
        return None

    values: list[float] = []
    with open(file_path) as f:
        lines = f.readlines()

    for line in lines[1:]:  # skip header
        parts = line.strip().split(";")
        if parts and parts[0].strip():
            values.append(round(float(parts[0].strip())))

    if len(values) < 2:
        logger.warning("Baseline displacement energy file has insufficient data")
        return None

    return Timeseries.from_values(start_date=parameters.start_date, frequency="1h", values=values)


def _load_specific_node_parameters(parameters: AntaresToAtlasParameters) -> dict[str, tuple[int, float]]:
    """Load node-specific EV parameters from CSV: columns [node_name, shift_hours, scale_factor]."""
    if parameters.disp_energy_node_parameters is None:
        logger.warning("disp_energy_node_parameters parameter not set")
        return {}

    file_path = Path(parameters.disp_energy_node_parameters)
    if not file_path.exists():
        logger.warning(f"Node parameters file not found: {file_path}")
        return {}

    params: dict[str, tuple[int, float]] = {}
    with open(file_path) as f:
        lines = f.readlines()

    for line in lines[1:]:  # skip header
        parts = line.strip().split(";")
        if len(parts) >= 3:
            node = parts[0].lower().strip()
            try:
                shift_h = int(parts[1].strip())
                scale = float(parts[2].strip())
                params[node] = (shift_h, scale)
            except ValueError:
                logger.warning(f"Invalid EV node parameters for node '{parts[0]}': {parts[1:]}")

    return params


def _compute_displacement_energy(
    area_id: str,
    baseline_ts: Timeseries | None,
    specific_node_parameters: dict[str, tuple[int, float]],
    start_date,
) -> Timeseries | None:
    """Scale baseline displacement energy by node scale factor and shift index by node shift hours."""
    if baseline_ts is None or area_id not in specific_node_parameters:
        return None

    shift_h, scale = specific_node_parameters[area_id]
    scaled_values = [round(v * scale) for v in baseline_ts.values]

    if len(scaled_values) < 2:
        return None

    shifted_start = start_date.subtract(hours=shift_h)
    return Timeseries.from_values(start_date=shifted_start, frequency="1h", values=scaled_values)


def _convert_standard_evs(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    baseline_displacement_energy_ts: Timeseries | None,
    specific_node_parameters: dict[str, tuple[int, float]],
) -> list[Storage]:
    """Convert standard EV units for all areas except France."""
    logger.info("Converting standard EV units")

    areas = study.get_areas()
    links = study.get_links()
    binding_constraints = study.get_binding_constraints()
    ev_units: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        if area_name.lower() == "fr":
            continue

        area = areas[area_name]
        thermals = area.get_thermals()

        # Cluster name pattern: "{area}_{area}_ve_inj" (lowercased from "{area}_{AREA}_VE_inj")
        ev_inj_name = f"{area_name}_{area_name}_ve_inj"
        ev_inj_thermal = thermals.get(ev_inj_name, None)
        if not ev_inj_thermal:
            logger.debug(f"No EV injection thermal '{ev_inj_name}' found for area {area_name}, skipping")
            continue

        ev_link = links.get(f"{area_name}_ve_eu", None)
        if not ev_link:
            logger.debug(f"No EV link '{area_name}_ve_eu' found for area {area_name}, skipping")
            continue

        ev_stock_bc = binding_constraints.get(f"ve_stock_{area_name}", None)
        if not ev_stock_bc:
            logger.debug(f"No binding constraint 've_stock_{area_name}' found, skipping EV for area {area_name}")
            continue

        ev_stor_name = f"ve_vhr_storage_ve_vhr_storage_ve_{area_name}_1"
        ev_stor_thermal = thermals.get(ev_stor_name, None)
        if not ev_stor_thermal:
            logger.debug(f"No EV storage thermal '{ev_stor_name}' found for area {area_name}, skipping")
            continue

        scenario = (
            study.get_output(parameters.output_name)
            .get_thermal_ts_numbers(area_name, ev_inj_name)
            .get(parameters.scenario, None)
        )
        if scenario is None:
            logger.warning(f"No scenario found for EV in area {area_name}, skipping")
            continue

        try:
            max_power_vals = ev_inj_thermal.get_series_matrix()[scenario - 1]
            max_energy_vals = ev_stor_thermal.get_series_matrix()[scenario - 1]

            maximum_power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=max_power_vals)
            maximum_energy_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=max_energy_vals)

            if maximum_power_ts.abs().max() == 0.0 or maximum_energy_ts.abs().max() == 0.0:
                continue

            # MinimumPower = -1 * link direct capacity (first scenario, capacity is constant)
            min_power_vals = ev_link.get_capacity_direct()[0]
            minimum_power_ts = Timeseries.from_values(
                parameters.start_date, frequency="1h", values=min_power_vals * -1.0
            )

        except Exception as e:
            logger.warning(f"Could not get time series for EV in area {area_name}: {e}")
            continue

        # Efficiencies from ve_stock BC weights (positional: [0]=charge, [1]=discharge)
        bc_weights = get_cluster_weights_from_bc(study, f"ve_stock_{area_name}")
        weights = list(bc_weights.values())
        charge_efficiency = abs(weights[0]) if weights else 1.0
        discharge_efficiency = abs(1.0 / weights[1]) if len(weights) > 1 and weights[1] != 0 else 1.0

        displacement_energy_ts = _compute_displacement_energy(
            area_name, baseline_displacement_energy_ts, specific_node_parameters, parameters.start_date
        )

        ev = Storage(
            name=f"{area_name}_ev",
            node=atlas_dataset.get("node", area_name),
            portfolio=atlas_dataset.get(
                "portfolio",
                f"generator_{area_name}" if parameters.consumption_production_separation else f"portfolio_{area_name}",
            ),
            storage_type=StorageType.ELECTRIC_VEHICLE,
            is_v2g=True,
            maximum_power=maximum_power_ts,
            minimum_power=minimum_power_ts,
            maximum_energy=maximum_energy_ts,
            minimum_state_of_charge=Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.3,
            ),
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency,
            storage_initial_level=parameters.storage.ev_initial_level,
            displacement_energy=displacement_energy_ts,
        )
        ev_units.append(ev)
        logger.debug(f"Created EV for area: {area_name}")

    logger.info("Standard EV conversion done")
    return ev_units


def _convert_france_evs(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    baseline_displacement_energy_ts: Timeseries | None,
    specific_node_parameters: dict[str, tuple[int, float]],
) -> list[Storage]:
    """Convert France EV units (night-only and regular).

    France has special EV modeling:
    - Night-only EVs: capacities multiplied by the night ratio (derived from binding constraints)
    - Regular EVs: residual capacity after subtracting the night share
    """
    logger.info("Converting FR EV units")

    areas = study.get_areas()
    links = study.get_links()
    binding_constraints = study.get_binding_constraints()
    ev_units: list[Storage] = []

    if "fr" not in areas:
        return ev_units

    area = areas["fr"]
    thermals = area.get_thermals()

    ev_inj_name = "fr_fr_ve_inj"
    ev_inj_thermal = thermals.get(ev_inj_name, None)
    if not ev_inj_thermal:
        logger.warning(f"FR EV: No injection thermal '{ev_inj_name}' found, skipping")
        return ev_units

    ev_stor_name = "ve_vhr_storage_ve_vhr_storage_ve_fr_1"
    ev_stor_thermal = thermals.get(ev_stor_name, None)
    if not ev_stor_thermal:
        logger.warning(f"FR EV: No storage thermal '{ev_stor_name}' found, skipping")
        return ev_units

    ev_link_total = links.get("fr_ve_fr_load_total", None)
    if not ev_link_total:
        logger.warning("FR EV: No link 'fr_ve_fr_load_total' found, skipping")
        return ev_units

    ve_fr_load_min_bc = binding_constraints.get("ve_fr_load_min", None)
    ve_fr_night_load_min_bc = binding_constraints.get("ve_fr_night_load_min", None)
    ve_stock_fr_bc = binding_constraints.get("ve_stock_fr", None)

    if not (ve_fr_load_min_bc and ve_fr_night_load_min_bc and ve_stock_fr_bc):
        logger.warning("FR EV: Missing one or more required binding constraints, skipping")
        return ev_units

    scenario = (
        study.get_output(parameters.output_name)
        .get_thermal_ts_numbers("fr", ev_inj_name)
        .get(parameters.scenario, None)
    )
    if scenario is None:
        logger.warning("FR EV: No scenario found for fr_fr_ve_inj, skipping")
        return ev_units

    try:
        ev_inj_vals = ev_inj_thermal.get_series_matrix()[scenario - 1]
        ev_stor_vals = ev_stor_thermal.get_series_matrix()[scenario - 1]
    except Exception as e:
        logger.warning(f"FR EV: Could not get series data: {e}")
        return ev_units

    # Night connection capacity: normalized binary-like timeseries (0/1)
    night_cap_arr = ev_link_total.get_capacity_direct()[0]
    max_cap = night_cap_arr.max()
    night_connection_arr = night_cap_arr / max_cap if max_cap != 0 else night_cap_arr

    # Night-only EV ratio from binding constraints:
    # where ve_fr_load_min > 0: ratio = ve_fr_night_load_min / ve_fr_load_min
    load_min_arr = Timeseries(ve_fr_load_min_bc.get_greater_term_matrix()).values
    night_load_min_arr = Timeseries(ve_fr_night_load_min_bc.get_greater_term_matrix()).values

    raw_ratio = np.where(load_min_arr != 0, night_load_min_arr / load_min_arr, 0.0)
    night_only_ev_ratio: float = float(raw_ratio.mean())

    # Per-timestep ratio timeseries: night_connection * ratio where load_min != 0
    ratio_ts_arr = np.where(load_min_arr != 0, night_connection_arr * night_only_ev_ratio, 0.0)

    # Efficiencies from ve_stock_fr BC weights (positional: [0]=charge, [2]=discharge)
    bc_weights = get_cluster_weights_from_bc(study, "ve_stock_fr")
    weights = list(bc_weights.values())
    charge_efficiency = abs(weights[0]) if weights else 1.0
    discharge_efficiency = abs(1.0 / weights[2]) if len(weights) > 2 and weights[2] != 0 else 1.0

    portfolio_name = "generator_fr" if parameters.consumption_production_separation else "portfolio_fr"
    portfolio = atlas_dataset.get("portfolio", portfolio_name)
    node = atlas_dataset.get("node", "fr")

    # MinimumPower requires ROW balance of virtual node ve_fr_load_total (output data)
    try:
        row_balance_arr = (
            study.get_output(parameters.output_name).get_mc_ind_area(
                mc_year=parameters.scenario,
                frequency=Frequency.HOURLY,
                data_type=MCIndAreasDataType.VALUES,
                area="ve_fr_load_total",
            )[("ROW BAL.", "MWh")],
        )  # TODO verify column name in antares craft output API

    except Exception as e:
        logger.warning(f"FR EV: Could not get ROW balance for ve_fr_load_total: {e}. Setting MinimumPower to 0.")
        row_balance_arr = np.zeros(len(ev_inj_vals))

    # --- Night-only EV ---
    night_max_power = np.round(ratio_ts_arr * ev_inj_vals).tolist()
    night_min_power = np.round(ratio_ts_arr * row_balance_arr).tolist()

    night_max_energy_raw = np.round(ratio_ts_arr * ev_stor_vals)
    # Forward-fill zeros so that MaximumEnergy stays constant during hours the unit is off
    # (legacy "Quick Fix": Antares sets MaximumEnergy=0 during day, Atlas disables unit via MaximumPower)
    night_max_energy: list[float] = []
    for v in night_max_energy_raw:
        if v == 0.0 and night_max_energy:
            night_max_energy.append(night_max_energy[-1])
        else:
            night_max_energy.append(float(v))

    shifted_disp_ts = _compute_displacement_energy(
        "fr", baseline_displacement_energy_ts, specific_node_parameters, parameters.start_date
    )
    if shifted_disp_ts is not None:
        night_disp_ts: Timeseries | None = (shifted_disp_ts * night_only_ev_ratio).round()
    else:
        night_disp_ts = None

    night_ev = Storage(
        name="fr_ev_night",
        node=node,
        portfolio=portfolio,
        storage_type=StorageType.ELECTRIC_VEHICLE,
        is_v2g=True,
        maximum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=night_max_power),
        minimum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=night_min_power),
        maximum_energy=Timeseries.from_values(parameters.start_date, frequency="1h", values=night_max_energy),
        minimum_state_of_charge=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.3,
        ),
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        storage_initial_level=parameters.storage.ev_initial_level,
        displacement_energy=night_disp_ts,
    )
    ev_units.append(night_ev)

    # --- Regular EV ---
    regular_max_power = np.round(ev_inj_vals - ratio_ts_arr * ev_inj_vals).tolist()
    regular_min_power = np.round(row_balance_arr - ratio_ts_arr * row_balance_arr).tolist()
    regular_max_energy = (ev_stor_vals - ratio_ts_arr * ev_stor_vals).tolist()

    if shifted_disp_ts is not None and night_disp_ts is not None:
        regular_disp_ts: Timeseries | None = (shifted_disp_ts - night_disp_ts).round()
    else:
        regular_disp_ts = None

    regular_ev = Storage(
        name="fr_ev_regular",
        node=node,
        portfolio=portfolio,
        storage_type=StorageType.ELECTRIC_VEHICLE,
        is_v2g=True,
        maximum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=regular_max_power),
        minimum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=regular_min_power),
        maximum_energy=Timeseries.from_values(parameters.start_date, frequency="1h", values=regular_max_energy),
        minimum_state_of_charge=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.3,
        ),
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        storage_initial_level=parameters.storage.ev_initial_level,
        displacement_energy=regular_disp_ts,
    )
    ev_units.append(regular_ev)

    logger.info("FR EV conversion done")
    return ev_units


def _convert_france_heavy_vehicles(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> list[Load]:
    """Convert France heavy vehicles (mobilite lourde) as Load equipment."""
    logger.info("Converting FR heavy vehicles")

    links = study.get_links()
    hv_link = links.get("fr_ve_fr_mobilite_lourde", None)

    if not hv_link:
        logger.debug("No heavy vehicle link 'fr_ve_fr_mobilite_lourde' found for FR")
        return []

    try:
        # CalculatedTransit is an MC output, not an input capacity
        transit_df = study.get_output(parameters.output_name).get_mc_ind_link(
            parameters.scenario,
            frequency=Frequency.HOURLY,
            data_type=MCIndLinksDataType.VALUES,
            area_from=hv_link.area_from_id,
            area_to=hv_link.area_to_id,
        )[("FLOW LIN.", "MWh")]
        maximum_power_ts = Timeseries.from_values(
            parameters.start_date,
            frequency="1h",
            values=transit_df,
            dtype=float * -1,
        )
    except Exception as e:
        logger.warning(f"Could not get transit data for FR heavy vehicles: {e}")
        return []

    hv = Load(
        name="fr_heavy_vehicles",
        node=atlas_dataset.get("node", "fr"),
        portfolio=atlas_dataset.get(
            "portfolio",
            "supplier_fr" if parameters.consumption_production_separation else "portfolio_fr",
        ),
        load_type=LoadType.OTHER_NON_DISPATCHABLE_LOAD,
        maximum_power_forecast=ForecastingMatrix().add(parameters.execution_date, maximum_power_ts),
    )

    logger.info("FR heavy vehicles conversion done")
    return [hv]
