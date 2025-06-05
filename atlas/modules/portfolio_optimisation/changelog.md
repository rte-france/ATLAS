## Version 1.1.0
* Added ImbalancePenaltyOffset
    * Impacts global_parameters.py, PO_functions.py (imbalance price calculation)
    * Led to a change in the sign of the objective function for the imbalance down price (lines 161 PO_solver.py)
* Separated Non-dispatchable Load (NDL, previously NDC) and flexible load
    * Added PO_load_constraints.py and PO_load.py (previously only NDC—NonDispatchable Consumption)
* P2G corrections
* Added comment by Florent Cogen in PO_hydraulic_constraints.py -- to analyze
* Renamed PO_storage_constraints.py correctly
* Added if statement to PO_storage_constraints.py to ignore storage with MaximumEnergy of 0 (offline à priori)
* Added if debug statement to reduce prints
* Correction to constraint names
    * Some did not previously include equipment name, meaning they were not created for the majority of plants in portfolio mode
* GlobalTimeSeries() replaced by GetForecast()
* Corrections to maxGradient calculation
    * Was not previously corrected for timestep size
* Added changelog.md and readme.md

## Previous

### Edit Florent 03/08/2022
* Properties modification to fit in ATLAS v1.1.5 model
* Addition of UseForecast parameter, and of related parts in the module. This parameter indicates when the Portfolio Optimization is used as a tool to generate Price Forecasts (for instance, during the Intraday market process).
* PV and Wind Equipments are now separated from Non Dispatchable Equipments. Their output isn't fixed anymore, and can vary between the value indicated in MaximumPowerForecast and MaximumPowerForecast * (1 - MaximumCurtailmentRatio).
* Power property is now updated for all Equipments, except for NonDispatchable.
* StoredEnergy is now updated for Hydraulic and Storage Equipments.
* StorageAdditionalHours is divided into 3 parameters to better represent differences between Storage types: BatteryAdditionalHours, PumpedHydraulicStorageAdditionalHours, ElectricVehicleAdditionalHours
