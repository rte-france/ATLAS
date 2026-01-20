"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Parameters for Antares to Atlas conversion module.
"""

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from atlas.io_utils.parameters import Parameters


class AntaresToAtlasParameters(Parameters):
    """Parameters for Antares to Atlas data conversion.

    This class defines all configuration needed to convert Antares simulation data
    to Atlas format, including version-specific and hypothesis-specific settings.

    :param antares_version: Version of Antares (e.g., "8.2", "8.6")
    :type antares_version: str
    :param hypothesis: Hypothesis identifier (e.g., "BP23" for Bilan Prévisionnel 2023)
    :type hypothesis: str
    :param market_areas: List of market areas to convert (e.g., ["fr", "de", "es"])
    :type market_areas: list[str]
    :param scenario: Scenario number to extract from Antares
    :type scenario: int
    :param verbose: Enable verbose logging
    :type verbose: bool
    :param excluded_thermic_groups: List of thermic groups to exclude from conversion
    :type excluded_thermic_groups: list[str]
    :param minimum_price: Minimum price for optimization (€/MWh)
    :type minimum_price: float
    :param maximum_price: Maximum price for optimization (€/MWh)
    :type maximum_price: float
    :param wind_max_curtailment_ratio: Maximum curtailment ratio for wind (0-1)
    :type wind_max_curtailment_ratio: float
    :param pv_max_curtailment_ratio: Maximum curtailment ratio for PV (0-1)
    :type pv_max_curtailment_ratio: float
    :param wind_curtailment_cost: Cost of wind curtailment (€/MWh)
    :type wind_curtailment_cost: float
    :param pv_curtailment_cost: Cost of PV curtailment (€/MWh)
    :type pv_curtailment_cost: float
    :param use_hydro_heuristic: Use heuristic for hydro management
    :type use_hydro_heuristic: bool
    :param hydro_min_energy_coeff: Minimum energy coefficient for hydro
    :type hydro_min_energy_coeff: float
    :param hydro_max_energy_coeff: Maximum energy coefficient for hydro
    :type hydro_max_energy_coeff: float
    :param use_water_value: Enable water value calculation
    :type use_water_value: bool
    :param water_value_scenarios: Number of scenarios for water value
    :type water_value_scenarios: int
    :param water_value_nb_years: Number of years for water value calculation
    :type water_value_nb_years: int
    :param hydro_storage_subdivision: Storage subdivision for water value
    :type hydro_storage_subdivision: int
    :param hydro_initialization_curve: Path to hydro initialization curve file
    :type hydro_initialization_curve: Path | None
    :param beta: Beta parameter for water value Bellman computation
    :type beta: float
    :param water_value_time_step: Time step for water value (hours)
    :type water_value_time_step: int
    :param use_bellman_interpolation: Use interpolation in Bellman computation
    :type use_bellman_interpolation: bool
    :param nb_storage_levels: Number of storage levels for water value
    :type nb_storage_levels: int
    :param inflows_time_step: Time step for inflows (hours)
    :type inflows_time_step: int
    :param path_inflows: Path to inflows data directory
    :type path_inflows: Path | None
    :param hydro_reservoirs_file: Path to hydraulic reservoirs configuration file
    :type hydro_reservoirs_file: Path | None
    :param hydraulic_fragments_file: Path to hydraulic fragments configuration file
    :type hydraulic_fragments_file: Path | None
    :param battery_initial_level: Initial level for battery storage (0-1)
    :type battery_initial_level: float
    :param ev_initial_level: Initial level for electric vehicle storage (0-1)
    :type ev_initial_level: float
    :param phs_initial_level: Initial level for pumped hydro storage (0-1)
    :type phs_initial_level: float
    :param baseline_displacement_energy: Path to baseline displacement energy file
    :type baseline_displacement_energy: Path | None
    :param disp_energy_node_parameters: Path to displacement energy node parameters file
    :type disp_energy_node_parameters: Path | None
    :param thermic_config_file: Path to thermic parameters configuration file
    :type thermic_config_file: Path | None
    :param consumption_production_separation: Enable separation of consumption and production portfolios
    :type consumption_production_separation: bool
    :param co2_emission_factors_file: Path to CO2 emission factors file
    :type co2_emission_factors_file: Path | None
    :param use_multi_energy: Enable multi-energy modeling
    :type use_multi_energy: bool
    :param enable_standard_conversions: Enable standard conversion steps
    :type enable_standard_conversions: bool
    :param enable_specific_conversions: Enable hypothesis-specific conversion steps
    :type enable_specific_conversions: bool
    :param conversion_steps: Specific conversion steps to execute (if empty, use defaults)
    :type conversion_steps: list[str]
    """

    # Version and hypothesis
    antares_version: str = Field(description="Antares version (e.g., '8.2', '8.6')")
    hypothesis: str = Field(description="Hypothesis identifier (e.g., 'BP23', 'BP24')")

    # Data selection
    market_areas: list[str] = Field(description="List of market areas to convert")
    scenario: int = Field(ge=1, description="Scenario number (1-based)")
    excluded_thermic_groups: list[str] = Field(default_factory=list, description="Thermic groups to exclude")

    # Economic parameters
    minimum_price: float = Field(default=-500.0, description="Minimum price (€/MWh)")
    maximum_price: float = Field(default=3000.0, description="Maximum price (€/MWh)")

    # RES curtailment
    wind_max_curtailment_ratio: float = Field(default=1.0, ge=0.0, le=1.0, description="Max wind curtailment ratio")
    pv_max_curtailment_ratio: float = Field(default=1.0, ge=0.0, le=1.0, description="Max PV curtailment ratio")
    wind_curtailment_cost: float = Field(default=0.01, description="Wind curtailment cost (€/MWh)")
    pv_curtailment_cost: float = Field(default=0.01, description="PV curtailment cost (€/MWh)")

    # Hydro management
    use_hydro_heuristic: bool = Field(default=True, description="Use hydro heuristic")
    hydro_min_energy_coeff: float = Field(default=0.0, description="Hydro min energy coefficient")
    hydro_max_energy_coeff: float = Field(default=1.0, description="Hydro max energy coefficient")

    # Water value
    use_water_value: bool = Field(default=False, description="Enable water value computation")
    water_value_scenarios: int = Field(default=1, ge=1, description="Number of water value scenarios")
    water_value_nb_years: int = Field(default=2, ge=2, description="Number of years for water value")
    hydro_storage_subdivision: int = Field(default=1, ge=1, description="Storage subdivision for water value")
    beta: float = Field(default=0.0, description="Beta parameter for Bellman computation")
    water_value_time_step: int = Field(default=168, ge=1, description="Water value time step (hours)")
    use_bellman_interpolation: bool = Field(default=False, description="Use Bellman interpolation")
    nb_storage_levels: int = Field(default=100, ge=1, description="Number of storage levels")
    inflows_time_step: int = Field(default=168, ge=1, description="Inflows time step (hours)")

    # File paths
    hydro_initialization_curve: Path | None = Field(default=None, description="Hydro initialization curve file")
    path_inflows: Path | None = Field(default=None, description="Path to inflows directory")
    hydro_reservoirs_file: Path | None = Field(default=None, description="Hydraulic reservoirs file")
    hydraulic_fragments_file: Path | None = Field(default=None, description="Hydraulic fragments file")
    baseline_displacement_energy: Path | None = Field(default=None, description="Baseline displacement energy file")
    disp_energy_node_parameters: Path | None = Field(default=None, description="Displacement energy node parameters")
    thermic_config_file: Path | None = Field(default=None, description="Thermic parameters file")
    co2_emission_factors_file: Path | None = Field(default=None, description="CO2 emission factors file")

    # Storage initial levels
    battery_initial_level: float = Field(default=0.5, ge=0.0, le=1.0, description="Battery initial level")
    ev_initial_level: float = Field(default=0.5, ge=0.0, le=1.0, description="EV initial level")
    phs_initial_level: float = Field(default=0.5, ge=0.0, le=1.0, description="PHS initial level")

    # Portfolio settings
    consumption_production_separation: bool = Field(
        default=False, description="Separate consumption and production portfolios"
    )
    use_multi_energy: bool = Field(default=False, description="Enable multi-energy modeling")

    # Conversion control
    enable_standard_conversions: bool = Field(default=True, description="Enable standard conversions")
    enable_specific_conversions: bool = Field(default=True, description="Enable specific conversions")
    conversion_steps: list[str] = Field(default_factory=list, description="Specific steps to execute (empty = all)")

    @field_validator("market_areas")
    @classmethod
    def validate_market_areas(cls, v: list[str]) -> list[str]:
        """Validate that market areas list is not empty."""
        if not v:
            raise ValueError("market_areas cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_file_paths(self) -> Self:
        """Validate that referenced files exist if provided."""
        file_fields = [
            "hydro_initialization_curve",
            "hydro_reservoirs_file",
            "hydraulic_fragments_file",
            "baseline_displacement_energy",
            "disp_energy_node_parameters",
            "thermic_config_file",
            "co2_emission_factors_file",
        ]

        for field_name in file_fields:
            file_path = getattr(self, field_name)
            if file_path is not None:
                path = Path(file_path)
                if not path.exists():
                    raise ValueError(f"{field_name}: File not found at {path}")

        if self.path_inflows is not None:
            inflows_path = Path(self.path_inflows)
            if not inflows_path.exists() or not inflows_path.is_dir():
                raise ValueError(f"path_inflows: Directory not found at {inflows_path}")

        return self
