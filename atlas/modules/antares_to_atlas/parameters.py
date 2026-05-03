"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Parameters for Antares to Atlas conversion module.
"""

from pathlib import Path
from typing import Literal

from pendulum import Duration, duration
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_extra_types.pendulum_dt import DateTime
from typing_extensions import Self

from atlas.enums import ThermalStrategy
from atlas.io_utils.parameters import Parameters
from atlas.validators import convert_to_duration


class ThermalTechnologyConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    minimum_stable_power_duration: Duration = duration(hours=0)
    startup_delay_probability: float = 0.0
    startup_duration: Duration = duration(hours=0)
    shutdown_duration: Duration = duration(hours=0)
    maximum_gradient: float = 0.0
    strategy: ThermalStrategy = ThermalStrategy.BASE
    setup_delay: float = 0.0

    @field_validator("minimum_stable_power_duration", "startup_duration", "shutdown_duration", mode="before")
    @classmethod
    def parse_duration(cls, v):
        return convert_to_duration(v)


class ThermalParameters(BaseModel):
    nuclear: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(hours=2),
            startup_delay_probability=0.82,
            startup_duration=duration(hours=10),
            shutdown_duration=duration(hours=10),
            maximum_gradient=25,
            strategy=ThermalStrategy.BASE,
            setup_delay=0,
        )
    )
    lignite: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(minutes=30),
            startup_delay_probability=0.41,
            startup_duration=duration(hours=10),
            shutdown_duration=duration(hours=10),
            maximum_gradient=5,
            strategy=ThermalStrategy.BASE,
            setup_delay=0,
        )
    )
    oil: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(hours=0),
            startup_delay_probability=0.59,
            startup_duration=duration(minutes=15),
            shutdown_duration=duration(minutes=15),
            maximum_gradient=10,
            strategy=ThermalStrategy.PEAK,
            setup_delay=0,
        )
    )
    gas: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(minutes=15),
            startup_delay_probability=0.26,
            startup_duration=duration(minutes=30),
            shutdown_duration=duration(minutes=30),
            maximum_gradient=30,
            strategy=ThermalStrategy.INTERMEDIATE,
            setup_delay=0.5,
        )
    )
    hard_coal: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(minutes=30),
            startup_delay_probability=0.41,
            startup_duration=duration(hours=1),
            shutdown_duration=duration(hours=1),
            maximum_gradient=5,
            strategy=ThermalStrategy.INTERMEDIATE,
            setup_delay=0,
        )
    )
    ccgt: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(minutes=15),
            startup_delay_probability=0.26,
            startup_duration=duration(hours=1),
            shutdown_duration=duration(hours=1),
            maximum_gradient=30,
            strategy=ThermalStrategy.INTERMEDIATE,
            setup_delay=0,
        )
    )
    ocgt: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(minutes=15),
            startup_delay_probability=0.26,
            startup_duration=duration(minutes=24),
            shutdown_duration=duration(minutes=24),
            maximum_gradient=10,
            strategy=ThermalStrategy.PEAK,
            setup_delay=0,
        )
    )

    pcomp_mid: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(minutes=30),
            startup_delay_probability=0.26,
            startup_duration=duration(hours=1),
            shutdown_duration=duration(hours=1),
            maximum_gradient=30.0,
            strategy=ThermalStrategy.INTERMEDIATE,
            setup_delay=0.0,
        )
    )
    pcomp_peak: ThermalTechnologyConfig = Field(
        default_factory=lambda: ThermalTechnologyConfig(
            minimum_stable_power_duration=duration(hours=0),
            startup_delay_probability=0.26,
            startup_duration=duration(minutes=24),
            shutdown_duration=duration(minutes=24),
            maximum_gradient=30.0,
            strategy=ThermalStrategy.PEAK,
            setup_delay=0.0,
        )
    )

    mixed_fuel_group: str = Field(
        default="Mixed_fuel", description="Antares group name identifying mixed fuel clusters"
    )
    waste_identifier: str = Field(
        default="Waste", description="Keyword in cluster name identifying waste sub-technology"
    )

    def get(self, name: str) -> ThermalTechnologyConfig | None:
        _ALIASES = {"coal": "hard_coal", "hard coal": "hard_coal"}
        key = name.lower()
        key = _ALIASES.get(key, key)
        return getattr(self, key, None)


class Co2EmissionFactors(BaseModel):
    nuclear: float = Field(default=0.0, description="Nuclear CO2 emission factor (tCO2/MWh)")
    lignite: float = Field(default=0.0, description="Lignite CO2 emission factor (tCO2/MWh)")
    hard_coal: float = Field(default=0.0, description="Hard coal CO2 emission factor (tCO2/MWh)")
    gas: float = Field(default=0.0, description="Gas CO2 emission factor (tCO2/MWh)")
    oil: float = Field(default=0.0, description="Oil CO2 emission factor (tCO2/MWh)")
    mixed_fuel: float = Field(default=0.0, description="Mixed fuel CO2 emission factor (tCO2/MWh)")
    other_1: float = Field(default=0.0, description="Other 1 CO2 emission factor (tCO2/MWh)")
    other_2: float = Field(default=0.0, description="Other 2 CO2 emission factor (tCO2/MWh)")
    other_3: float = Field(default=0.0, description="Other 3 CO2 emission factor (tCO2/MWh)")
    other_4: float = Field(default=0.0, description="Other 4 CO2 emission factor (tCO2/MWh)")

    def get(self, group: str) -> float | None:
        key = group.lower().replace(" ", "_")
        return getattr(self, key, None)


class DsrTypeConfig(BaseModel):
    name: str
    bc_name: str | None = None
    thermal_name: str
    has_daily_constraint: bool


class DsrParameters(BaseModel):
    fr_types: list[DsrTypeConfig] = Field(
        default_factory=lambda: [
            DsrTypeConfig(
                name="fr_dsr_indus",
                bc_name="fr_dsr_industrie_stock",
                thermal_name="fr_FR_DSR_industrie",
                has_daily_constraint=True,
            ),
            DsrTypeConfig(
                name="fr_dsr_tert",
                bc_name="fr_dsr_tertiaire_stock",
                thermal_name="fr_FR_DSR_tertiaire",
                has_daily_constraint=True,
            ),
            DsrTypeConfig(
                name="fr_dsr_implicite",
                bc_name=None,
                thermal_name="fr_FR_DSR_implicite",
                has_daily_constraint=False,
            ),
        ]
    )
    other_bc_pattern: str = Field(
        default="dsr_{area_id}_stock",
        description="Binding constraint name pattern for non-FR DSR (use {area_id})",
    )
    other_thermal_pattern: str = Field(
        default="{area_id}_{area_upper}_DSR_0",
        description="Thermal cluster name pattern for non-FR DSR (use {area_id}, {area_upper})",
    )


class StorageParameters(BaseModel):
    battery_initial_level: float = Field(default=0.5, ge=0.0, le=1.0, description="Battery initial level")
    ev_initial_level: float = Field(default=0.5, ge=0.0, le=1.0, description="EV initial level")
    phs_initial_level: float = Field(default=0.5, ge=0.0, le=1.0, description="PHS initial level")
    battery_normal_link: str = Field(
        default="z_batteries", description="Antares link name for normal batteries virtual node"
    )
    battery_pcomp_link: str = Field(
        default="z_batteries_pcomp", description="Antares link name for PCOMP batteries virtual node"
    )


class ResParameters(BaseModel):
    wind_max_curtailment_ratio: float = Field(default=1.0, ge=0.0, le=1.0, description="Max wind curtailment ratio")
    pv_max_curtailment_ratio: float = Field(default=1.0, ge=0.0, le=1.0, description="Max solar curtailment ratio")
    wind_curtailment_cost: float = Field(default=0.01, description="Wind curtailment cost (€/MWh)")
    pv_curtailment_cost: float = Field(default=0.01, description="Solar curtailment cost (€/MWh)")
    wind_onshore_group: str = Field(
        default="wind onshore", description="Antares renewable group name for wind onshore clusters"
    )
    wind_offshore_suffix: str = Field(
        default="_wind_offshore", description="Suffix appended to area name to find offshore wind cluster"
    )
    wind_offshore_excluded_areas: list[str] = Field(
        default=["dekf", "dkkf"], description="Areas excluded from offshore wind capacity merging"
    )
    solar_pv_group: str = Field(default="solar pv", description="Antares renewable group name for solar PV clusters")
    solar_thermo_suffix: str = Field(
        default="_solar_thermo", description="Suffix appended to area name to find solar thermal cluster"
    )


class OutputParameters(BaseModel):
    marginal_price_column: str = Field(
        default="MRG. PRICE", description="MC output column name for area marginal price"
    )
    misc_ndg_column: str = Field(
        default="MISC. NDG", description="MC output column name for misc non-dispatchable generation"
    )
    ror_column: str = Field(default="H. ROR", description="MC output column name for run-of-river hydro generation")


class HydroReservoirConfig(BaseModel):
    reservoir_capacity: float = 0.0
    open_loop_capacity: float = 0.0
    closed_loop_capacity: float = 0.0


class HydroFragmentConfig(BaseModel):
    prices: list[float]
    volumes: list[float]


def _default_reservoirs() -> dict[str, HydroReservoirConfig]:
    _data = {
        "at": (770000, 1700000, 2000),
        "be": (0, 0, 6000),
        "ch": (8100000, 0, 670000),
        "cz": (2500, 2300, 3700),
        "de": (260000, 420000, 350000),
        "dkw": (0, 0, 0),
        "es": (11600000, 6000000, 100000),
        "fr": (10000000, 90000, 10000),
        "ukgb": (0, 0, 26000),
        "ie": (0, 0, 1700),
        "itca": (572000, 0, 0),
        "itcn": (187000, 0, 0),
        "itcs": (800000, 100000, 4300),
        "itn": (3700000, 194000, 31000),
        "its": (154000, 0, 0),
        "itsar": (144000, 0, 7800),
        "itsic": (81000, 20000, 7400),
        "lu": (0, 0, 5000),
        "ukni": (0, 0, 0),
        "nl": (0, 0, 0),
        "nom": (0, 8600000, 0),
        "non": (0, 21300000, 0),
        "nos": (0, 57300000, 0),
        "pl": (800, 1500, 6300),
        "pt": (1290000, 2018000, 0),
        "se1": (14430000, 0, 0),
        "se2": (14800000, 0, 0),
        "se3": (2635000, 0, 0),
        "se4": (71000, 0, 0),
    }
    return {
        node: HydroReservoirConfig(
            reservoir_capacity=rc,
            open_loop_capacity=ol,
            closed_loop_capacity=cl,
        )
        for node, (rc, ol, cl) in _data.items()
    }


def _default_fragments() -> dict[str, HydroFragmentConfig]:
    _generic = HydroFragmentConfig(
        prices=[-25.963, -15.631, -7.411, 11.13, 20.769, 30.889, 39.475],
        volumes=[0.0569, 0.1742, 0.23, 0.1213, 0.3121, 0.0514, 0.0541],
    )
    return {
        "Generic": _generic,
        "fr": HydroFragmentConfig(
            prices=[-25.963, -15.631, -7.411, 11.13, 20.769, 30.889, 39.475],
            volumes=[0.0569, 0.1742, 0.23, 0.1213, 0.3121, 0.0514, 0.0541],
        ),
    }


class HydroParameters(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Management
    use_heuristic: bool = Field(default=True, description="Use hydro heuristic")
    min_energy_coeff: float = Field(default=0.0, description="Hydro min energy coefficient")
    max_energy_coeff: float = Field(default=1.0, description="Hydro max energy coefficient")

    # Water value
    max_water_value: float = Field(default=26000.0, description="Maximum water value cap (€/MWh)")
    use_water_value: bool = Field(default=False, description="Enable water value computation")
    water_value_scenarios: list[str] | Literal["all"] = Field(
        default_factory=list, description="Water value scenario identifiers, or 'all'"
    )
    water_value_nb_years: int = Field(default=2, ge=2, description="Number of years for water value")
    storage_subdivision: int = Field(default=1, ge=1, description="Storage subdivision for water value")
    beta: float = Field(default=0.0, description="Beta parameter for Bellman computation")
    water_value_timestep: Duration = Field(default=duration(hours=1), description="Water value time step (hours)")
    use_bellman_interpolation: bool = Field(default=False, description="Use Bellman interpolation")
    nb_storage_levels: int = Field(default=100, ge=1, description="Number of storage levels")
    inflows_timestep: Duration = Field(default=duration(hours=168), description="Inflows time step (hours)")

    # File paths
    initialization_curve: Path | None = Field(default=None, description="Hydro initialization curve file")
    path_inflows: Path | None = Field(default=None, description="Path to inflows directory")

    # Per-node data
    reservoirs: dict[str, HydroReservoirConfig] = Field(default_factory=_default_reservoirs)
    fragments: dict[str, HydroFragmentConfig] = Field(default_factory=_default_fragments)

    def get_reservoir(self, node: str) -> HydroReservoirConfig | None:
        return self.reservoirs.get(node)

    def get_fragment(self, area: str) -> HydroFragmentConfig:
        return self.fragments.get(area) or self.fragments["Generic"]

    @field_validator("inflows_timestep", "water_value_timestep", mode="before")
    @classmethod
    def parse_duration(cls, v):
        return convert_to_duration(v)

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        if self.initialization_curve is not None and not Path(self.initialization_curve).exists():
            raise ValueError(f"initialization_curve: File not found at {self.initialization_curve}")
        if self.path_inflows is not None:
            p = Path(self.path_inflows)
            if not p.exists() or not p.is_dir():
                raise ValueError(f"path_inflows: Directory not found at {self.path_inflows}")
        return self


class AntaresToAtlasParameters(Parameters):
    """Parameters for Antares to Atlas data conversion.

    This class defines all configuration needed to convert Antares simulation data
    to Atlas format, including version-specific and hypothesis-specific settings.
    """

    # Version and hypothesis
    start_date: DateTime
    execution_date: DateTime
    hypothesis: str | None = Field(None, description="Hypothesis identifier (e.g., 'BP23', 'BP24')")
    output_name: str

    # Data selection
    market_areas: list[str] = Field(description="List of market areas to convert")
    scenario: int = Field(
        1,
        description=" Name of the Monte-Carlo scenario. This number must match the name of the MC year that should be converted from Antares",
    )
    excluded_thermic_groups: list[str] = Field(default_factory=list, description="Thermic groups to exclude")

    # Economic parameters
    minimum_price: float = Field(default=-500.0, description="Minimum price (€/MWh)")
    maximum_price: float = Field(default=3000.0, description="Maximum price (€/MWh)")

    renewables: ResParameters = Field(default_factory=ResParameters, description="Renewable energy parameters")
    hydro: HydroParameters = Field(default_factory=HydroParameters, description="Hydraulic parameters")
    storage: StorageParameters = Field(
        default_factory=StorageParameters, description="Storage initial level parameters"
    )
    thermal: ThermalParameters = Field(
        default_factory=ThermalParameters, description="Per-technology thermal parameters"
    )
    baseline_displacement_energy: Path | None = Field(default=None, description="Baseline displacement energy file")
    disp_energy_node_parameters: Path | None = Field(default=None, description="Displacement energy node parameters")
    co2_emission_factors: Co2EmissionFactors = Field(
        default_factory=Co2EmissionFactors, description="Per-technology CO2 emission factors (tCO2/MWh)"
    )
    dsr: DsrParameters = Field(default_factory=DsrParameters, description="DSR unit configurations")
    output: OutputParameters = Field(default_factory=OutputParameters, description="MC output column names")

    # Portfolio settings
    consumption_production_separation: bool = Field(
        default=False, description="Separate consumption and production portfolios"
    )
    use_multi_energy: bool = Field(default=False, description="Enable multi-energy modeling")

    # Conversion control
    conversion_steps: list[str] = Field(default_factory=list, description="Specific steps to execute (empty = all)")

    @field_validator("hypothesis")
    @classmethod
    def uppercase_hypothesis(cls, v: str | None) -> str | None:
        """Convert hypothesis to uppercase."""
        if v is not None:
            return v.upper()
        return v

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
            "baseline_displacement_energy",
            "disp_energy_node_parameters",
        ]

        for field_name in file_fields:
            file_path = getattr(self, field_name)
            if file_path is not None:
                path = Path(file_path)
                if not path.exists():
                    raise ValueError(f"{field_name}: File not found at {path}")

        return self
