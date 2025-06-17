import os

import API
from PO_functions import (
    check_output_path,
    get_date_to_clean_string,
    get_deltaT_to_string,
    get_parameter_date,
)
from System import DateTime


# ------ Create the Parameters class
class Parameters:
    # Static list of all attributes

    # Default constructor
    def __init__(self, output_marker):
        # --- General parameters
        # Informations and debug
        self.debug = API.IO.GetParameterByIdentifier("Debug").Value
        self.verbose = API.IO.GetParameterByIdentifier("Verbose").Value

        # Dates and timeframes
        self.start_date = get_parameter_date("StartDate")
        self.original_end_date = get_parameter_date("EndDate")

        # We truncate the seconds to allow action plan tasks to share a common ExecDate if necessary
        # This should in particular reduce compute time by avoiding interpolation in GetForecast calls
        execution_date = get_parameter_date("ExecutionDate")
        self.execution_date = DateTime(
            execution_date.Year,
            execution_date.Month,
            execution_date.Day,
            execution_date.Hour,
            execution_date.Minute,
            0,
        )

        self.time_step = API.IO.GetParameterByIdentifier("TimeStep").Value
        self.time_step_str = get_deltaT_to_string(self.time_step / 60.0)

        # Update end_date
        # FC: clean this later, too many changes in the code for now but this offset is more confusing than helpful
        self.end_date = self.original_end_date.AddMinutes(-self.time_step)

        # Optim periods
        self.target_times = API.DatetimeIndex.NewIndex(self.start_date, self.end_date, self.time_step_str)
        self.original_target_times = API.DatetimeIndex.NewIndex(
            self.start_date, self.original_end_date, self.time_step_str
        )

        self.optimization_period = len(self.target_times) + int(
            API.IO.GetParameterByIdentifier("AdditionalHours").Value * 60.0 / self.time_step
        )
        self.thermal_optimization_period = len(self.target_times) + int(
            API.IO.GetParameterByIdentifier("ThermalAdditionalHours").Value * 60.0 / self.time_step
        )
        self.hydraulic_optimization_period = len(self.target_times) + int(
            API.IO.GetParameterByIdentifier("HydraulicAdditionalHours").Value * 60.0 / self.time_step
        )
        self.battery_optimization_period = len(self.target_times) + int(
            API.IO.GetParameterByIdentifier("BatteryAdditionalHours").Value * 60.0 / self.time_step
        )
        self.phs_optimization_period = len(self.target_times) + int(
            API.IO.GetParameterByIdentifier("PumpedHydraulicStorageAdditionalHours").Value * 60.0 / self.time_step
        )
        self.ev_optimization_period = len(self.target_times) + int(
            API.IO.GetParameterByIdentifier("ElectricVehicleAdditionalHours").Value * 60.0 / self.time_step
        )

        self.op_times = API.DatetimeIndex.NewIndex(self.start_date, self.optimization_period, self.time_step_str)
        self.thermal_op_times = API.DatetimeIndex.NewIndex(
            self.start_date, self.thermal_optimization_period, self.time_step_str
        )
        self.hydraulic_op_times = API.DatetimeIndex.NewIndex(
            self.start_date, self.hydraulic_optimization_period, self.time_step_str
        )
        self.battery_op_times = API.DatetimeIndex.NewIndex(
            self.start_date, self.battery_optimization_period, self.time_step_str
        )
        self.phs_op_times = API.DatetimeIndex.NewIndex(
            self.start_date, self.phs_optimization_period, self.time_step_str
        )
        self.ev_op_times = API.DatetimeIndex.NewIndex(self.start_date, self.ev_optimization_period, self.time_step_str)

        self.init_battery_time = self.start_date.AddMinutes(-self.time_step)

        # --- Market parameters
        # Excluded areas / technologies / thermal strategies
        excluded_market_areas_raw = API.IO.GetParameterByIdentifier("ExcludedMarketAreas").Value
        if excluded_market_areas_raw == "All":
            self.excluded_market_areas = [
                market_area.Name for market_area in output_marker.Market.MarketArea.GetAllInstances()
            ]
        elif not excluded_market_areas_raw or excluded_market_areas_raw == "None":
            self.excluded_market_areas = []
        else:
            self.excluded_market_areas = [
                market_area_name.strip() for market_area_name in excluded_market_areas_raw.split(";")
            ]

        excluded_techno_raw = API.IO.GetParameterByIdentifier("ExcludedTechnologies").Value
        if excluded_techno_raw == "All":
            namespace = output_marker.GetNamespaceByName("Equipment")
            self.excluded_technologies = [techno.Name for techno in namespace.GetAllClasses()]
        elif not excluded_techno_raw or excluded_techno_raw == "None":
            self.excluded_technologies = []
        else:
            self.excluded_technologies = [techno.strip() for techno in excluded_techno_raw.split(";")]

        excluded_thermal_strat_raw = API.IO.GetParameterByIdentifier("ExcludedThermalStrategies").Value
        if excluded_thermal_strat_raw == "All":
            self.excluded_thermal_strategies = ["Base", "Intermediate", "Peak"]
        elif not excluded_thermal_strat_raw or excluded_thermal_strat_raw == "None":
            self.excluded_thermal_strategies = []
        else:
            self.excluded_thermal_strategies = [
                strat_name.strip() for strat_name in excluded_thermal_strat_raw.split(";")
            ]

        # Imbalances
        self.small_imbalance_size = API.IO.GetParameterByIdentifier("SmallImbalanceSize").Value
        self.small_imbalance_penalty = API.IO.GetParameterByIdentifier("SmallImbalancePenalty").Value
        self.large_imbalance_penalty = API.IO.GetParameterByIdentifier("LargeImbalancePenalty").Value
        self.max_overall_imbalance = API.IO.GetParameterByIdentifier("MaximumImbalance").Value
        self.imbalance_penalty_offset = API.IO.GetParameterByIdentifier("ImbalancePenaltyOffset").Value
        self.isp_forecast_lower_bound = API.IO.GetParameterByIdentifier("ISPForecastLowerBound").Value

        # Reserves parameters
        self.automated_unprocured_reserves_penalty = API.IO.GetParameterByIdentifier(
            "AutomatedUnprocuredReservesPenalty"
        ).Value
        self.manual_unprocured_reserves_penalty = API.IO.GetParameterByIdentifier(
            "ManualUnprocuredReservesPenalty"
        ).Value

        # Others
        self.is_portfolio_bidding = API.IO.GetParameterByIdentifier("IsPortfolioBidding").Value

        self.market = API.IO.GetParameterByIdentifier("Market").Value
        if self.market not in ["DayAhead", "Intraday", "RRActivation", "MFRRActivation"]:
            API.IO.Trace.Log(
                "Market parameter is invalid. Please look at its description for more informations",
                API.IO.LogTypeError,
            )

        self.use_forecast = API.IO.GetParameterByIdentifier("UseForecast").Value

        # --- Technology specific parameters
        # Hydraulic parameters
        self.hydro_minimal_fragment_size = API.IO.GetParameterByIdentifier("HydraulicMinimalFragmentSize").Value

        # Storage parameters
        self.phs_nb_fragments = API.IO.GetParameterByIdentifier("PumpedHydraulicNumberOfFragments").Value
        self.phs_smoothing_factor = API.IO.GetParameterByIdentifier("PumpedHydraulicSmoothingFactor").Value
        self.phs_reserve_duration = API.IO.GetParameterByIdentifier("PumpedHydraulicReserveDuration").Value

        self.ev_nb_fragments = API.IO.GetParameterByIdentifier("ElectricVehicleNumberOfFragments").Value
        self.ev_smoothing_factor = API.IO.GetParameterByIdentifier("ElectricVehicleSmoothingFactor").Value
        self.ev_reserve_duration = API.IO.GetParameterByIdentifier("ElectricVehicleReserveDuration").Value

        self.battery_nb_fragments = API.IO.GetParameterByIdentifier("BatteryNumberOfFragments").Value
        self.battery_smoothing_factor = API.IO.GetParameterByIdentifier("BatterySmoothingFactor").Value
        self.battery_reserve_duration = API.IO.GetParameterByIdentifier("BatteryReserveDuration").Value
        self.automated_battery_reserve_duration = API.IO.GetParameterByIdentifier(
            "BatteryAutomatedReserveDuration"
        ).Value

        # Solver and general parameters
        self.allowed_round_off_error = API.IO.GetParameterByIdentifier("AllowedRoundOffError").Value

        # --- Optimization and Solver parameters
        self.solver = API.IO.GetParameterByIdentifier("Solver").Value
        self.presolve = API.IO.GetParameterByIdentifier("UsePresolve").Value
        self.time_out = API.IO.GetParameterByIdentifier("SolverTimeOut").Value
        self.duality_gap = API.IO.GetParameterByIdentifier("SolverDualityGap").Value
        self.with_rounding = API.IO.GetParameterByIdentifier("WithRounding").Value

        # LP output folder
        output_folder = API.IO.GetParameterByIdentifier("OutputFolder").Value
        if not output_folder:
            output_folder = "PO"

        output_folder_2 = os.path.join(API.UserSharedFolder, output_folder)
        if self.debug:
            check_output_path(output_folder_2)

        output_folder_3 = os.path.join(output_folder_2, self.market)
        if self.debug:
            check_output_path(output_folder_3)

        self.output_folder = os.path.join(output_folder_3, get_date_to_clean_string(self.execution_date))
        if self.debug:
            check_output_path(self.output_folder)
