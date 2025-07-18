# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Package Management
- **Install dependencies**: `uv sync`
- **Install dev dependencies**: `uv sync --dev`

### Code Quality
- **Linting**: `ruff check`
- **Format code**: `ruff format`
- **Type checking**: `mypy`
- **Run tests**: `pytest`
- **Run tests with coverage**: `pytest --cov=atlas --cov-report=html`

### Documentation
- **Build docs**: `mkdocs build`
- **Serve docs locally**: `mkdocs serve`
- **Deploy docs**: `mike deploy --push --update-aliases <version> latest`

### Application
- **Run Atlas CLI**: `atlas` (main entry point)
- **Check version**: `atlas version`

## Code Architecture

### Core Structure
Atlas is a power market simulation tool with a modular architecture:

**Main Components:**
- `atlas/` - Main package containing core modules
- `atlas/abstract_class/` - Abstract base classes defining interfaces
- `atlas/math/` - Mathematical objects (Timeseries, Matrix, etc.)
- `atlas/models/` - Business models for equipment and market structures
- `atlas/modules/` - Simulation modules (portfolio optimization, etc.)
- `atlas/workflow/` - Workflow orchestration system
- `atlas/solver/` - Optimization solver interfaces
- `atlas/io_utils/` - Data loading and processing utilities

### Key Abstractions

**AbstractModule**: Base class for simulation modules with standardized lifecycle:
- `create_parameters()` - Parse raw parameters
- `import_data()` - Load input data
- `validate_data()` - Validate inputs
- `execute()` - Main module logic
- `validates_results()` - Validate outputs
- `export_results()` - Export results

**AbstractDataset**: Base class for input/output datasets with generic typing

**Workflow System**: Sequential execution of modules
- `Workflow` - Manages execution of multiple workflow steps
- `WorkflowStep` - Individual step wrapping a module
- Each step's output becomes the next step's input

### Data Handling

**Mathematical Objects:**
- `Timeseries` - Time series data using Polars backend
- `Matrix` - Matrix operations for optimization
- `LazyMatrix`/`LazyTimeseries` - Lazy evaluation for performance
- `ScenarioMatrix`/`ForecastingMatrix` - Specialized matrix types

**Business Models:**
- Equipment models: `Hydro`, `Thermal`, `Solar`, `Wind`, `Storage`, `Load`
- Market models: `MarketArea`, `MarketBorder`, `Order`, `Portfolio`
- Network models: `Node`, `ControlBlock`

### Portfolio Optimization Module

Main simulation module located in `atlas/modules/portfolio_optimisation/`:
- `PortfolioOptimisationModel` - Core optimization logic
- Equipment-specific models in `models/` directory
- Constraint building and variable management
- Integration with OR-Tools solver

## Data Structure

### Input Data
- `data/atlas-dataset/` - Contains datasets for different market types:
  - `day-ahead/` - Day-ahead market data
  - `market-clearing/` - Market clearing data
  - `portfolio-optimisation/` - Portfolio optimization data
- Data organized by: `objects/`, `timeseries/`, `scenario_matrix/`, `forecasting_matrix/`
- Format: CSV for objects, Parquet for time series data

### Configuration
- `parameters.yaml` - Main configuration file for simulation parameters
- `pyproject.toml` - Project configuration, dependencies, and tool settings

## Testing

### Test Structure
- `tests/test_unit/` - Unit tests organized by module
- `tests/test_workflow/` - Integration tests for workflows
- Uses pytest framework
- Coverage reporting with pytest-cov

### Running Tests
```bash
pytest                           # Run all tests
pytest tests/test_unit/          # Run unit tests only
pytest -k "test_name"            # Run specific test
pytest --cov=atlas              # Run with coverage
```

## Development Guidelines

### Code Standards
- Python 3.10+ required
- Line length: 120 characters (configured in ruff)
- Use type hints extensively
- Follow existing import patterns and module structure

### Key Dependencies
- **Data**: polars, pandas, pyarrow, fastparquet
- **Optimization**: ortools
- **CLI**: typer
- **Validation**: pydantic
- **Logging**: loguru
- **Time**: pendulum
- **Plotting**: plotly

### Module Development
When creating new modules:
1. Inherit from `AbstractModule`
2. Implement all abstract methods
3. Create corresponding input/output dataset classes
4. Add proper parameter validation
5. Include comprehensive logging
6. Add unit tests following existing patterns

### Working with Optimization
- Use `OptimisationModel` wrapper around OR-Tools
- Equipment models add variables and constraints
- Portfolio models coordinate equipment optimization
- Handle solver failures gracefully with manual activation fallback
