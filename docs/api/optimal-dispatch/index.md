# Optimal Dispatch

Shared dispatch layer used by the Day-Ahead Orders and Portfolio Optimisation modules. See the
[Optimal Dispatch section](../../optimal-dispatch/index.md) for the concepts and the usage guide.

## Dispatch

- [:lucide-fire: **ThermalDispatch**](thermal.md) — thermal operating states, ramps and minimum times
- [:lucide-battery-charging: **StorageDispatch**](storage.md) — charge/discharge, state of charge, cycle balance
- [:lucide-waves: **HydroDispatch**](hydro.md) — reservoir energy balance and bid fragments
- [:lucide-wind: **RenewableDispatch**](renewable.md) — forecast-driven bounds and curtailment
- [:lucide-plug: **LoadDispatch**](load.md) — consumption bounds

## Contracts

- [:lucide-clipboard-check: **Input objects**](input-objects.md) — the `*DispatchInput` models

## Reserves

- [:lucide-scale: **Reserve handlers**](reserves.md) — handlers and the factory

## Pricing

- [:lucide-droplet: **Marginal pricing**](marginal-pricing.md) — hydro water values

## Steps

- [:lucide-square-stack: **AbstractOptimStep**](steps.md) — the per-equipment step contract
