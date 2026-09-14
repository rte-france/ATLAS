# Reserve Products

This page is about the subject rather than the code: what balancing reserves are, what the four
products do, and why ATLAS collapses them into two families.

## Why reserves exist

An electrical grid stores almost nothing. Generation and consumption must match at every instant,
and the frequency is the measure of whether they do: too much generation and it rises above
50 Hz, too little and it falls.

Markets schedule that balance in advance, but the schedule is always wrong by the time it is
executed — a unit trips, the wind forecast was optimistic, consumption surprises. Reserves are
the capacity the system operator has arranged, ahead of time, to close that residual gap in real
time.

## The cascade

Four products act in sequence, each buying time for the next:

| Product | Name | What it does | Full activation | Activated by |
|---|---|---|---|---|
| **FCR** | Frequency Containment Reserve | Arrests the frequency drift and stabilises it at a new value — it does not bring it back to 50 Hz | seconds | the unit itself, automatically, in proportion to the frequency deviation |
| **aFRR** | automatic Frequency Restoration Reserve | Returns the frequency to 50 Hz and the control area to its schedule, freeing FCR for the next event | a few minutes | an automatic signal sent continuously by the TSO |
| **mFRR** | manual Frequency Restoration Reserve | Relieves aFRR for larger or longer imbalances | ~15 minutes | a dispatch order from the TSO |
| **RR** | Replacement Reserve | Replaces activated FRR so it is available again, for prolonged events | ~30 minutes | a dispatch order from the TSO |

Activation times are orders of magnitude for Continental Europe. The binding figures are set per
synchronous area and per LFC block, and differ between TSOs — check the applicable network code
rather than this table if the exact value matters.

Each product is also procured and exchanged through its own European platform (FCR Cooperation,
PICASSO, MARI, TERRE), which is where the `MarketType` values `mfrr_activation` and
`rr_activation` come from.

## Two economic layers

Reserve is paid for twice, and the distinction matters when reading module outputs:

- **Capacity** — being available. Procured ahead of delivery, remunerated whether or not the
  reserve is ever called. This is what the dispatch decision is about: holding megawatts back
  costs the opportunity of selling them as energy.
- **Energy** — being activated. Remunerated per MWh actually delivered when the TSO calls.

In the data model that split appears as `*_procured` (capacity contracted) versus `*_activated`
(energy delivered) on equipment, portfolios and control blocks.

## Why ATLAS groups them in two

The layer does not model four products. It models two families:

$$
\text{automated} = \text{FCR} + \text{aFRR}
\qquad
\text{manual} = \text{mFRR} + \text{RR}
$$

The grouping is not a simplification for convenience — it follows the only distinction the
*dispatch* problem can see.

**Automated reserve** is activated without anyone deciding anything about that particular unit:
the governor responds to frequency, or the TSO's control loop sends a signal to everything
enrolled. From the dispatch's point of view, the only question is whether the unit is
*technically able* to respond right now. A thermal unit that is off, climbing its startup ramp or
shutting down is not, which is exactly what the
[capacity constraints](formulation.md#capacity-constraints) encode.

**Manual reserve** is dispatched by an operator choosing among offers. From the dispatch's point
of view it is capacity held in reserve that may be called — bounded by available power rather
than by an enrolment cap.

Within each family the products behave identically as far as the physics is concerned, so
modelling them separately would add variables without adding information.

!!! note "Both modules model both families"

    An earlier reading of the architecture had reserves as a Portfolio Optimisation concern
    absent from Day-Ahead Orders. That is not right: reserves are present in Day-Ahead Orders
    too, in exactly this automated/manual form. It is the reason the reserve handlers live in
    the common layer rather than in the Portfolio Optimisation module.

## What the data model carries

On [`Equipment`](../../api/models/equipment/equipment.md):

| Field | Meaning |
|---|---|
| `maximum_fcr`, `maximum_afrr` | Capability caps — the most this unit may be enrolled for. Summed into `maximum_automated` |
| `fcr_up_procured`, `fcr_down_procured` | Capacity contracted, per direction |
| `afrr_*_procured`, `mfrr_*_procured`, `rr_*_procured` | Same, for the other three products |
| `fcr_activated`, `afrr_activated`, `mfrr_activated`, `rr_activated` | Energy actually delivered |
| `*_submitted_volume` | Volumes offered |

Note the asymmetry: only FCR and aFRR have a *capability cap* field, because only the automated
family needs one — manual reserve is bounded by the unit's power, which the dispatch already
knows.

Aggregates live on [`Portfolio`](../../api/models/market_operator/portfolio.md) (procurement
summed over a portfolio's units) and on `ControlBlock` (the TSO's needs and the balancing costs).
`MarketArea` carries activation prices and post-clearing balances per product.

## What the modules configure

Reserve behaviour is driven by module parameters rather than by the common layer:

| Parameter | Module | Meaning |
|---|---|---|
| `automated_unprocured_reserves_penalty` | DAO, PO | Penalty (€/MW/h) for failing to provide automated reserve. Default 30 000 — deliberately high, so the solver treats it as a last resort |
| `manual_unprocured_reserves_penalty` | DAO, PO | Same, for manual reserve |
| `proportional_reserves_penalty` | DAO | Whether the offered reserve volume is flexible, with a proportional penalty, rather than fixed |
| `battery_reserve_duration`, `battery_automated_reserve_duration` | PO | How long a battery must be able to sustain the reserve. Default 60 min each |
| `electric_vehicle_reserve_duration`, `…_automated_…` | PO | Same for EVs. Default 1 min — an EV fleet is not expected to sustain reserve for long |
| `pumped_hydraulic_reserve_duration`, `…_automated_…` | PO | Same for pumped hydro. Default 60 min |

The **reserve duration** is what turns a power commitment into an energy requirement: promising
2 MW of a one-hour product means holding 2 MWh in the tank. It is the coefficient in the
[state-of-charge coupling constraints](formulation.md#storage).

See [Portfolio Optimisation parameters](../../modules/portfolio-optimisation/user-guide/parameters.md)
and [Day-Ahead Orders parameters](../../modules/day-ahead-orders/user-guide/parameters.md).

## Next

- [Formulation](formulation.md) — how this becomes variables and constraints.
- [Developer guide](developer.md) — how to build on it.
