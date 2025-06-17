* [String] StartDate: Beginning of the timeframe studied by the module.
NB: In action plan context, value is automatically set according to task settings, and should not be reconfigured in the parameters of the study case.
    * Default value: 2028/07/01 01:00:00
    * Advanced: False
    * Optional: False
* [String] ExecutionDate: Date from which the module is executed.
NB: In action plan context, value is automatically set according to task settings, and should not be reconfigured in the parameters of the study case.
    * Default value: 2028/06/30 13:00:00
    * Advanced: False
    * Optional: False
* [String] EndDate: End of the timeframe studied by the module. More precisely, the end of the last time step of this timeframe.
NB: In action plan context, value is automatically set according to task settings, and should not be reconfigured in the parameters of the study case.
    * Default value: 2028/07/01 03:00:00
    * Advanced: False
    * Optional: False
* [Boolean] Debug: Boolean indicating if the PO is in debug mode
    * Default value: False
    * Advanced: False
    * Optional: False
* [Boolean] IsPortfolioBidding: True if the optimization should be done on portofolios, or False if it should be done on individual units.
    * Default value: True
    * Advanced: False
    * Optional: False
* [Boolean] UseForecast: This boolean indicates whether to take a price forecast. If true, portfolio optimization happens before a market. If false, after a market.
    * Default value: False
    * Advanced: False
    * Optional: False
* [Boolean] UsePresolve: Boolean indicating if the solver should use a presolve mode or not.
    * Default value: False
    * Advanced: False
    * Optional: False
* [Boolean] Verbose: If True, information of the module execution will be displayed in the terminal.
    * Default value: True
    * Advanced: False
    * Optional: False
* [Boolean] WithRounding: If true, optimization outputs are rounded at the end of the module to avoid optimization artefacts.
    * Default value: True
    * Advanced: False
    * Optional: False
* [Double] AllowedRoundOffError: Error (in MW) below which the activated power is considered equal to 0.
    * Default value: 0.01
    * Advanced: False
    * Optional: False
* [Double] AutomatedUnprocuredReservesPenalty: A penalty expressed in euro/MW per hour corresponding to the price of not providing the  automated reserves
    * Default value: 30000
    * Advanced: False
    * Optional: False
* [Double] BatterySmoothingFactor: This factor will contribute in smoothing the power offer/demand curve. Value between 0 and 1.
    * Default value: 0.2
    * Advanced: False
    * Optional: False
* [Double] ElectricVehicleSmoothingFactor: This factor will contribute in smoothing the power offer/demand curve. Value between 0 and 1.
    * Default value: 0.2
    * Advanced: False
    * Optional: False
* [Double] ImbalancePenaltyOffset: Offset (in euros/MWh) applied when forecasting the imbalance settlement price.
    * Default value: 10
    * Advanced: False
    * Optional: False
* [Double] ISPForecastLowerBound: Lower bound (in euro/MWh) of the absolute value of the Imbalance Settlement Price forecast.
    * Default value: 10
    * Advanced: False
    * Optional: False
* [Double] LargeImbalancePenalty: Coefficient multiplied by the price of the last market in the area of each portfolio, used to estimate an imbalance settlement price for largeimbalances.
    * Default value: 0.2
    * Advanced: False
    * Optional: False
* [Double] MaximumImbalance: Maximum imbalance allowed within a portfolio, in MW
    * Default value: 100000
    * Advanced: False
    * Optional: False
* [Double] ManualUnprocuredReservesPenalty: A penalty expressed in euro/MW per hour corresponding to the price of not providing the  manual reserves
    * Default value: 30000
    * Advanced: False
    * Optional: False
* [Double] PumpedHydraulicSmoothingFactor: This factor will contribute in smoothing the power offer/demand curve. Value between 0 and 1.
    * Default value: 0.2
    * Advanced: False
    * Optional: False
* [Double] SmallImbalancePenalty: Coefficient multiplied by the price of the last market in the area of each portfolio, used to estimate an imbalance settlement price for small imbalances.
    * Default value: 0.1
    * Advanced: False
    * Optional: False
* [Double] SmallImbalanceSize: The quantity (in %) of imbalance qualified as small for the portfolio, relative to the maximum energy that the portfolio can produce
    * Default value: 0.15
    * Advanced: False
    * Optional: False
* [Double] SolverDualityGap: DualityGap used for the optimization. Default value should be 0.0001
    * Default value: 0.0001
    * Advanced: False
    * Optional: False
* [Integer] AdditionalHours: Default optimization period in hours, applied to PV, Wind and Load equipments. Specific optimization periods can be applied to Thermal, Hydraulic and Storage and will overwrite AdditionalHours
    * Default value: 12
    * Advanced: False
    * Optional: False
* [Integer] BatteryAdditionalHours: Optimization period in hours for Storage Equipments of type Battery
    * Default value: 24
    * Advanced: False
    * Optional: False
* [Integer] BatteryAutomatedReserveDuration: The automated reserve duration for battery equipement
    * Default value: 60
    * Advanced: False
    * Optional: False
* [Integer] BatteryNumberOfFragments: Number of power fragments; at each time step, power delivered is divided into fragments, last fragments are more expensive than first ones
    * Default value: 1
    * Advanced: False
    * Optional: False
* [Integer] BatteryReserveDuration: The manual reserve duration for battery equipement
    * Default value: 60
    * Advanced: False
    * Optional: False
* [Integer] ElectricVehicleAdditionalHours: Optimization period in hours for Storage Equipments of type ElectricVehicle
    * Default value: 24
    * Advanced: False
    * Optional: False
* [Integer] ElectricVehicleAutomatedReserveDuration: The automated reserve duration for electric vehicle equipement
    * Default value: 1
    * Advanced: False
    * Optional: False
* [Integer] ElectricVehicleNumberOfFragments:  Number of power fragments; at each time step, power delivered is divided into fragments, last fragments are more expensive than first ones
    * Default value: 1
    * Advanced: False
    * Optional: False
* [Integer] ElectricVehicleReserveDuration: The manual reserve duration for electric vehicle equipement
    * Default value: 0
    * Advanced: False
    * Optional: False
* [Integer] HydraulicAdditionalHours: Optimization period in hours for groupe
    * Default value: 12
    * Advanced: False
    * Optional: False
* [Integer] HydraulicMinimalFragmentSize: Minimal amount of power for an offer to be formulated. If for one particular time-step, the quantity Qmax of an offer is less than this threshold, the associated fragment is removed. Then the Qmax values of the other fragments are renormalized.
    * Default value: 100
    * Advanced: False
    * Optional: False
* [Integer] PumpedHydraulicAutomatedReserveDuration: The automated reserve duration for pumped hydraulic equipement
    * Default value: 60
    * Advanced: False
    * Optional: False
* [Integer] PumpedHydraulicNumberOfFragments: Number of power fragments; at each time step, power delivered is divided into fragments, last fragments are more expensive than first ones
    * Default value: 1
    * Advanced: False
    * Optional: False
* [Integer] PumpedHydraulicReserveDuration: The manual reserve duration for pumped hydraulic equipement
    * Default value: 60
    * Advanced: False
    * Optional: False
* [Integer] PumpedHydraulicStorageAdditionalHours: Optimization period in hours for Storage Equipments of type PumpedHydraulicStorage
    * Default value: 144
    * Advanced: False
    * Optional: False
* [Integer] SolverTimeout: Timeout (in seconds) of the optimization. Value by default: 240
    * Default value: 240
    * Advanced: False
    * Optional: False
* [Integer] ThermalAdditionalHours: Optimization period in hours for thermal groupe
    * Default value: 12
    * Advanced: False
    * Optional: False
* [Integer] TimeStep: Time step (in minutes) of the simulated market.
    * Default value: 60
    * Advanced: False
    * Optional: False
* [String] ExcludedMarketAreas: List of market areas (separated by ";") that should not be included in the classic portfolio optimization problem, but rather dealt with by a simple heuristic (accepting exactly what has been activated by the Clearing).. "None" and "All" are possible values.
    * Default value: None
    * Advanced: False
    * Optional: False
* [String] ExcludedTechnologies: List of equipment types (separated by ";") that should not be included in the classic portfolio optimization problem, but rather dealt with by a simple heuristic (accepting exactly what has been activated by the Clearing). "None" and "All" are possible values.
    * Default value: None
    * Advanced: False
    * Optional: False
* [String] ExcludedThermalStrategies: List of thermal strategies (separated by ";") for which the manual activation mode is always used. Possible values : "Peak", "Intermediate", "Base", "All", "None".
    * Default value: None
    * Advanced: False
    * Optional: False
* [String] Market: Market during which the Portfolio Optimization is run. Possible values are : "DayAhead", "Intraday", "RRActivation", "MFRRActivation".
    * Default value: DayAhead
    * Advanced: False
    * Optional: False
* [String] OutputFolder: Optional parameter to choose an output folder in the SAMBA folder where the LPs will be exported. If None, a folder will be created named "PO_{Market}_{ExecutionDate}".
    * Default value: PO
    * Advanced: False
    * Optional: False
* [String] Solver: GLPK(default), PNE, GLOP (for linear problems only), SCIP, CP-SAT
    * Default value: GLPK
    * Advanced: False
    * Optional: False
