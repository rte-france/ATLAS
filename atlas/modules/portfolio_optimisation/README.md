# Portfolio Optimisation Module

## Overview

The Portfolio Optimisation module optimizes energy asset portfolios by determining optimal bidding strategies and dispatch schedules across various market types. It supports multiple energy technologies including thermal plants, storage systems, renewable generation, and load management.

## Key Features

- **Multi-portfolio optimization**: Optimize entire portfolios or individual equipment units
- **Market flexibility**: Support for Day-Ahead, Intraday, and reserve activation markets
- **Technology support**: Thermal, hydro, storage (batteries, pumped hydro, EVs), solar, wind, and load
- **Constraint modeling**: Complex operational constraints including thermal unit commitment, storage cycling, and reserve requirements
- **Price forecasting**: Integration with market price forecasts and imbalance settlement price estimation
- **Solver flexibility**: Support for multiple solvers (XPRESS, PNE, GLOP, SCIP, CP-SAT)

## Module Structure

```
portfolio_optimisation/
├── module.py                 # Main module interface (AbstractModule implementation)
├── main.py                   # Orchestrator and optimization model
├── parameters.py             # Configuration parameters
├── input_dataset.py          # Input data handling
├── output_dataset.py         # Output data handling
├── models/                   # Equipment and portfolio models
│   ├── portfolio.py          # Portfolio model with variables/constraints
│   ├── portfolio_equipments.py  # Equipment container
│   ├── thermal/              # Thermal unit models (8 combinations)
│   ├── storage.py            # Battery, pumped hydro, EV models
│   ├── hydro.py              # Hydraulic generation
│   ├── solar.py              # Solar generation
│   ├── wind.py               # Wind generation
│   ├── load.py               # Load management
│   ├── market_area.py        # Market price context
│   └── control_block.py      # Control block constraints
└── utils/                    # Helper utilities
    ├── imbalance_price.py    # Imbalance price estimation
    ├── getters.py            # Data extraction utilities
    ├── variable_utils.py     # Variable management
    └── manual_activation.py  # Fallback activation logic
```

## Quick Start

### Basic Configuration

```python
from atlas.modules.portfolio_optimisation import PortfolioOptimisationModule
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters

# Configure parameters
params = PortfolioOptimisationParameters(
    start_date="2025-01-01",
    end_date="2025-01-02",
    timestep=duration(hours=1),
    market=MarketType.dayahead,
    solver=SolverEnum.XPRESS,
    is_portfolio_bidding=True,
    use_forecast=False
)

# Initialize module
module = PortfolioOptimisationModule()
```

### Running Optimization

```python
module.run(raw_data, params.model_dump())
```

## Key Parameters

### Optimization Modes

- `is_portfolio_bidding`: `True` for portfolio-level optimization, `False` for individual equipment
- `use_forecast`: `True` to make pre-market optimisation.
- `market`: Market type (DayAhead, Intraday, RRActivation, MFRRActivation)

### Solver Configuration

- `solver`: Solver choice (XPRESS, PNE, GLOP, SCIP, CP-SAT)
- `solver_timeout`: Timeout duration for optimization (default: 60s)
- `solver_duality_gap`: Optimization tolerance (default: 0.0001)
- `use_presolve`: Enable solver presolve mode

### Penalties and Limits

- `automated_unprocured_reserves_penalty`: Penalty for missing automated reserves (default: 30000 €/MW/h)
- `manual_unprocured_reserves_penalty`: Penalty for missing manual reserves (default: 30000 €/MW/h)
- `maximum_imbalance`: Maximum allowed portfolio imbalance (default: 100000 MW)
- `imbalance_penalty_offset`: ISP forecast offset (default: 10 €/MWh)

## Optimization Process

1. **Data Import**: Convert business objects to optimization-ready format
2. **Validation**: Check timestep consistency across all timeseries
3. **Model Building**:
   - Add variables for each equipment and portfolio
   - Add operational constraints
   - Build objective function (cost minimization/profit maximization)
4. **Solving**: Invoke solver with configured timeout
5. **Export**: Generate LP files and extract optimal solutions
