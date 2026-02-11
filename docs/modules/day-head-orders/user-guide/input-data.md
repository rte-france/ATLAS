# Parameters

## Overview

The Day-Ahead Orders module is configured through `DayAheadOrdersParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

## Required Parameters

These parameters are inherited from `AbstractParameters`:

- **`start_date`** (DateTime): Start of the optimization period
- **`end_date`** (DateTime): End of the optimization period
- **`execution_date`** (DateTime): Date when the optimization is executed

## Execution Parameters

- **`output_folder`** (str, default: ""): Path where the lp exports outputs are exported.

- **`verbose`** (bool, default: True): A boolean indicating whether the program shall return detailed logs.

## Optimization Parameters

### Solver configuration

- **`timestep`** (Duration, default: 1 hour): Discretization step of the simulated time interval

- **`solver_name`** (SolverEnum, default: `XPRESS`): Optimization solver to use
    * Options: `"XPRESS"`, `"PNE"`, `"GLOP"`, `"SCIP"`, `"CP-SAT"`

- **`export_lp`** (bool, default: False): Export solver LP files for debugging and analysis.

- **`solver_timeout`** (Duration, default: 4 minutes): Maximum solve time

- **`solver_duality_gap`** (float, default: 0.0001): Duality gap for optimization

- **`use_presolve`** (bool, default: False): Enable solver presolve mode

## Penalties & Pricing

### Reserve Penalties

- **`proportional_reserves_penalty`** (bool, default: true): Boolean indicating whether the amount of reserves offered is flexible, resulting in a proportional penalty priced to the market

- **`automated_unprocured_reserves_penalty`** (float, default: 10000): Penalty expressed in euros/MW per hour corresponding to the price of not providing the automated reserves procurement

- **`manual_unprocured_reserves_penalty`** (float, default: 100): Penalty expressed in euros/MW per hour corresponding to the price of not providing the manual reserves procurement.

## Storage Equipment Parameters

### Battery

- **`battery_nb_fragments`** (int, default: 3): Number of orders that can be formulated at one time-step for the optimization problem related to the Storage instances with the type Battery.

- **`battery_smoothing_factor`** (float, default: 0.1): Coefficient used to determine the extra cost of each power fragment in the optimization problem related to the Storage instances with the type Battery.

- **`battery_additional_hours`** (Duration, default: 48 hours): Number of extra hours after end date for the optimization programs applied to Storage instances with the type Battery.

### Pumped Hydraulic Storage

- **`phs_nb_fragments`** (int, default: 3): Number of orders that can be formulated at one time-step for the optimization problem related to the Storage instances with the type PumpedHydraulicStorage.

- **`phs_smoothing_factor`** (float, default: 0.2): Coefficient used to determine the extra cost of each power fragment in the optimization problem related to the Storage instances with the type PumpedHydraulicStorage.

- **`hydraulic_minimal_fragment_size`** (int, default: 100): Minimal amount of power for an offer to be formulated. If for one particular time-step, the quantity Qmax of an offer is less than this threshold, the associated fragment is removed. Then the Qmax values of the other fragments are renormalized.

- **`phs_additional_hours`** (Duration, default: 144 hours): Number of extra hours after end date for the optimization programs applied to Storage instances with the type PumpedHydraulicStorage.

### Electric Vehicle

- **`ev_nb_fragments`** (int, default: 3): Number of orders that can be formulated at one time-step for the optimization problem related to the Storage instances with the type ElectricVehicle.

- **`ev_smoothing_factor`** (float, default: 0.1): Coefficient used to determine the extra cost of each power fragment in the optimization problem related to the Storage instances with the type ElectricVehicle.

- **`ev_energy_coef`** (float, default: 1.5): Coefficient multiplied to the delta of DisplacementEnergy to compensate for over the entire EV optimization time frame, used to generate enough Buy offers.

- **`ev_additional_hours`** (Duration, default: 144 hours): Number of extra hours after end date for the optimization programs applied to Storage instances with the type ElectricVehicle.

### Load

- **`load_price`** (float, default: 3000): Price of all load orders (in euros/MWh). 3000 is a standard value, corresponding to the upper price cap of the DayAhead market.

### Thermal

- **`epsilon`** (float, default: 0.001): A slack parameter to avoid infeasibilities due to numerical approximations.

- **`price_forecasts_types`** (["Medium", "High", "Low"]): List of available PriceForecasts in the input data, separated by ';'. The default value should always include 'Medium'.

- **`thermal_additional_hours`** (Duration, default: 12 hours): Number of extra hours after end date for the optimization programs applied to Thermic instances.

## Example Configuration

```yml
start_date: "2028-09-27 00:00:00"
execution_date: "2028-09-26 12:00:00"
end_date: "2028-09-28 00:00:00"
output_folder: "./lp_exports"
proportional_reserves_penalty: True
use_presolve: True
automated_unprocured_reserves_penalty: 10000
battery_smoothing_factor: 0.1
ev_energy_coef: 1.5
ev_smoothing_factor: 0.1
epsilon: 0.001
hydraulic_minimal_fragment_size: 100
load_price: 3000
manual_unprocured_reserves_penalty: 100
phs_smoothing_factor: 0.2
solver_duality_gap: 0.0001
thermal_additional_hours: 12h
battery_additional_hours: 48h
battery_nb_fragments: 3
ev_additional_hours: 144h
ev_nb_fragments: 3
phs_additional_hours: 144h
phs_nb_fragments: 3
solver_timeout: 240s
timestep: 1h
price_forecasts_types: ["Medium"]
solver_name: "XPRESS"
export_lp: True
verbose: True
```

## Next Steps

- [Running](running.md): How to execute the module
