from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters


class PortfolioOptimizationParameters(AbstractParameters):
    """
    Parameters for configuring the portfolio optimization module.

    :param start_date: Beginning of the timeframe studied by the module.
    :type start_date: str
    :param execution_date: Date from which the module is executed.
    :type execution_date: str
    :param end_date: End of the timeframe studied by the module.
    :type end_date: str
    :param debug: Boolean indicating if the PO is in debug mode.
    :type debug: bool
    :param is_portfolio_bidding: True if the optimization should be done on portfolios, otherwise individual units.
    :type is_portfolio_bidding: bool
    :param use_forecast: Indicates whether to take a price forecast.
    :type use_forecast: bool
    :param use_presolve: Whether the solver should use presolve mode.
    :type use_presolve: bool
    :param verbose: If True, module execution information will be displayed.
    :type verbose: bool
    :param with_rounding: Whether optimization outputs are rounded at the end.
    :type with_rounding: bool
    :param min_gap: Value of the gap used in the solver.
    :type min_gap: float
    :param max_gap: Maximum value of the gap used in the solver.
    :type max_gap: float
    :param with_unit_start_cost: Enables cost of start/stop optimization.
    :type with_unit_start_cost: bool
    :param with_unit_min_up_down_time: Enables optimization of minimum up and down time.
    :type with_unit_min_up_down_time: bool
    :param with_unit_production_bound: Enables the use of maximum and minimum production constraints.
    :type with_unit_production_bound: bool
    :param with_unit_ramp: Enables ramp constraints.
    :type with_unit_ramp: bool
    :param with_unit_initial_state: Enables the use of initial states in optimization.
    :type with_unit_initial_state: bool
    :param with_unit_must_run: Enables "must run" constraints.
    :type with_unit_must_run: bool
    :param with_unit_energy: Enables optimization of energy constraints.
    :type with_unit_energy: bool
    :param with_portfolio_energy: Enables optimization of energy constraints at portfolio level.
    :type with_portfolio_energy: bool
    :param with_energy_max_min_duration: Enables the energy constraints over duration (min and max).
    :type with_energy_max_min_duration: bool
    :param with_energy_initial_state: Enables initial state for energy.
    :type with_energy_initial_state: bool
    :param with_energy_final_state: Enables final state for energy.
    :type with_energy_final_state: bool
    :param with_energy_weekly_final_state: Enables weekly final state for energy.
    :type with_energy_weekly_final_state: bool
    :param with_energy_sharing: Enables optimization of shared energy constraints.
    :type with_energy_sharing: bool
    :param with_energy_shared_variable: Enables optimization of shared energy through variables.
    :type with_energy_shared_variable: bool
    :param with_coupling_energy_power: Enables linking energy and power variables.
    :type with_coupling_energy_power: bool
    :param with_coupling_energy_energy: Enables linking energy constraints.
    :type with_coupling_energy_energy: bool
    :param with_coupling_initial_energy: Enables initialization of coupling energy.
    :type with_coupling_initial_energy: bool
    :param with_max_running_power: Enables constraints on maximum running power.
    :type with_max_running_power: bool
    :param with_min_running_power: Enables constraints on minimum running power.
    :type with_min_running_power: bool
    :param with_startup_constraints: Enables startup related constraints.
    :type with_startup_constraints: bool
    :param with_startup_cost: Enables cost of startup in objective function.
    :type with_startup_cost: bool
    :param with_objective_cost: Enables optimization with cost objective.
    :type with_objective_cost: bool
    :param with_objective_profit: Enables optimization with profit objective.
    :type with_objective_profit: bool
    :param with_objective_adjusted_profit: Enables optimization with adjusted profit objective.
    :type with_objective_adjusted_profit: bool
    :param with_objective_cash_flow: Enables optimization with cash flow objective.
    :type with_objective_cash_flow: bool
    :param with_objective_adjusted_cash_flow: Enables optimization with adjusted cash flow objective.
    :type with_objective_adjusted_cash_flow: bool
    :param with_cash_flow_revenue: Includes revenue in cash flow calculation.
    :type with_cash_flow_revenue: bool
    :param with_cash_flow_cost: Includes cost in cash flow calculation.
    :type with_cash_flow_cost: bool
    :param with_cash_flow_delta_stock: Includes stock delta in cash flow calculation.
    :type with_cash_flow_delta_stock: bool
    :param with_cash_flow_delta_margin: Includes margin delta in cash flow calculation.
    :type with_cash_flow_delta_margin: bool
    :param with_cash_flow_delta_contract: Includes contract delta in cash flow calculation.
    :type with_cash_flow_delta_contract: bool
    :param with_cash_flow_delta_capital: Includes capital delta in cash flow calculation.
    :type with_cash_flow_delta_capital: bool
    :param with_cash_flow_delta: Includes all deltas in cash flow calculation.
    :type with_cash_flow_delta: bool
    :param with_constraints: Enables constraints management globally.
    :type with_constraints: bool
    :param with_constraints_contract: Enables contract constraints.
    :type with_constraints_contract: bool
    :param with_constraints_margin: Enables margin constraints.
    :type with_constraints_margin: bool
    :param with_constraints_power: Enables power constraints.
    :type with_constraints_power: bool
    :param with_constraints_volume: Enables volume constraints.
    :type with_constraints_volume: bool
    :param with_constraints_commitment: Enables commitment constraints.
    :type with_constraints_commitment: bool
    :param with_contract_duration: Enables contract duration constraints.
    :type with_contract_duration: bool
    :param with_financial_constraints: Enables financial constraints globally.
    :type with_financial_constraints: bool
    :param with_cash_account: Enables cash account constraints.
    :type with_cash_account: bool
    :param with_credit_limit: Enables credit limit constraints.
    :type with_credit_limit: bool
    :param with_asset_transaction: Enables asset transaction modeling.
    :type with_asset_transaction: bool
    :param with_renewable_commitment: Enables renewable commitment constraints.
    :type with_renewable_commitment: bool
    """

    start_date: str = Field(default="2028/07/01 01:00:00")
    execution_date: str = Field(default="2028/06/30 13:00:00")
    end_date: str = Field(default="2028/07/01 03:00:00")
    debug: bool = Field(default=False)
    is_portfolio_bidding: bool = Field(default=True)
    use_forecast: bool = Field(default=False)
    use_presolve: bool = Field(default=False)
    verbose: bool = Field(default=True)
    with_rounding: bool = Field(default=True)

    min_gap: float = Field(default=0.01)
    max_gap: float = Field(default=0.10)

    with_unit_start_cost: bool = Field(default=True)
    with_unit_min_up_down_time: bool = Field(default=True)
    with_unit_production_bound: bool = Field(default=True)
    with_unit_ramp: bool = Field(default=True)
    with_unit_initial_state: bool = Field(default=True)
    with_unit_must_run: bool = Field(default=True)

    with_unit_energy: bool = Field(default=True)
    with_portfolio_energy: bool = Field(default=True)
    with_energy_max_min_duration: bool = Field(default=True)
    with_energy_initial_state: bool = Field(default=True)
    with_energy_final_state: bool = Field(default=True)
    with_energy_weekly_final_state: bool = Field(default=True)

    with_energy_sharing: bool = Field(default=True)
    with_energy_shared_variable: bool = Field(default=True)

    with_coupling_energy_power: bool = Field(default=True)
    with_coupling_energy_energy: bool = Field(default=True)
    with_coupling_initial_energy: bool = Field(default=True)

    with_max_running_power: bool = Field(default=True)
    with_min_running_power: bool = Field(default=True)

    with_startup_constraints: bool = Field(default=True)
    with_startup_cost: bool = Field(default=True)

    with_objective_cost: bool = Field(default=True)
    with_objective_profit: bool = Field(default=False)
    with_objective_adjusted_profit: bool = Field(default=False)
    with_objective_cash_flow: bool = Field(default=False)
    with_objective_adjusted_cash_flow: bool = Field(default=False)

    with_cash_flow_revenue: bool = Field(default=True)
    with_cash_flow_cost: bool = Field(default=True)
    with_cash_flow_delta_stock: bool = Field(default=True)
    with_cash_flow_delta_margin: bool = Field(default=True)
    with_cash_flow_delta_contract: bool = Field(default=True)
    with_cash_flow_delta_capital: bool = Field(default=True)
    with_cash_flow_delta: bool = Field(default=True)

    with_constraints: bool = Field(default=True)
    with_constraints_contract: bool = Field(default=True)
    with_constraints_margin: bool = Field(default=True)
    with_constraints_power: bool = Field(default=True)
    with_constraints_volume: bool = Field(default=True)
    with_constraints_commitment: bool = Field(default=True)
    with_contract_duration: bool = Field(default=True)

    with_financial_constraints: bool = Field(default=True)
    with_cash_account: bool = Field(default=True)
    with_credit_limit: bool = Field(default=True)

    with_asset_transaction: bool = Field(default=True)
    with_renewable_commitment: bool = Field(default=True)
