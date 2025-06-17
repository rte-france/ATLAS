from __future__ import annotations

from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters


class PortfolioOptimizationConfig(AbstractParameters):
    debug: bool = Field(default=False, description="Boolean indicating if the PO is in debug mode.")
    is_portfolio_bidding: bool = Field(
        default=True,
        description="True if the optimization should be done on portfolios, False if on individual units.",
    )
    consider_constraints_for_kpis: bool = Field(
        default=False,
        description="If true, KPIs are computed taking into account constraints on the bids (capa, ramps, etc.)",
    )
    consider_only_units_from_candidates: bool = Field(
        default=False,
        description="If true, the optimization considers only units in the candidate portfolios.",
    )
    non_conformities_enabled: bool = Field(
        default=True, description="If true, the optimization accounts for non-conformities."
    )
    auto_assign_units: bool = Field(
        default=True,
        description="If true, units are automatically assigned to portfolios without a user-defined assignment.",
    )
    check_input_integrity: bool = Field(
        default=True,
        description="If true, an integrity check of the inputs is performed before the optimization.",
    )
    check_input_integrity_level: int = Field(
        default=3, description="Controls the intensity of the integrity check (1=light, 3=full)."
    )
    output_folder: str = Field(default="outputs", description="Path to the folder where outputs will be written.")
    constraint_threshold: float = Field(
        default=1e-5, description="Threshold for relaxing constraints to avoid numerical issues."
    )
    use_storage_for_clearing: bool = Field(
        default=False,
        description="If true, storage units can be used in the market clearing algorithm.",
    )
    write_excel_outputs: bool = Field(
        default=False, description="If true, optimization results are exported as Excel files."
    )
    verbose: bool = Field(default=True, description="If true, more information is printed during optimization.")
    legacy_costs: bool = Field(default=False, description="If true, the optimization uses the legacy cost computation.")
    enable_min_bid_size_constraint: bool = Field(
        default=True,
        description="If true, applies a minimum bid size constraint to the optimization.",
    )
    validate_profiles: bool = Field(
        default=True, description="If true, profiles are validated before the optimization."
    )
    enable_foresight_validation: bool = Field(
        default=True, description="If true, foresight is validated for all units."
    )
    drop_virtual_units: bool = Field(
        default=True, description="If true, virtual units are dropped from the optimization."
    )
    update_inputs: bool = Field(
        default=True,
        description="If true, input files are updated with results from the optimization.",
    )
    enable_target_energy: bool = Field(
        default=False,
        description="If true, allows the setting of target energy constraints in the optimization.",
    )
    aggregate_at_portfolio_level: bool = Field(
        default=False, description="If true, KPIs are aggregated at the portfolio level."
    )
    enable_soft_constraints: bool = Field(default=True, description="If true, enables the use of soft constraints.")
    write_json_outputs: bool = Field(
        default=False, description="If true, optimization results are exported in JSON format."
    )
    capacity_constraint_model: str = Field(
        default="strict",
        description="Model to be used for capacity constraints. Options might include 'strict' or 'relaxed'.",
    )
    consider_emissions: bool = Field(
        default=False,
        description="If true, emissions constraints or KPIs are considered in the optimization.",
    )
    enable_spinning_reserve: bool = Field(
        default=False, description="If true, spinning reserve requirements are enforced."
    )
    write_extended_kpis: bool = Field(
        default=False, description="If true, additional KPIs (extended) are calculated and written."
    )
    write_debug_data: bool = Field(
        default=False, description="If true, writes detailed debug data for further analysis."
    )
    force_solver: str | None = Field(
        default=None,
        description="Force a specific solver (e.g. 'cbc', 'glpk', 'gurobi') to be used.",
    )
