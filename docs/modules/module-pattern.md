# ATLAS Module Pattern

## Overview

All ATLAS modules follow the `AbstractModule` pattern, providing a consistent interface for data processing, validation, execution, and result export.

## Standard Module Interface

Every ATLAS module is run through `ModuleRun`, which executes the module lifecycle
and applies the resulting change sets back onto the dataset:

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.<module_name> import <ModuleName>Module

input_data = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=<ModuleName>Module(),
    dataset=input_data,
    parameters="path/to/parameters.yml",
).run()
```

!!! warning "Always go through `ModuleRun`"
    Calling `module.run(...)` directly only executes the lifecycle — it does **not**
    apply the produced change sets. `ModuleRun.run()` wraps it with the `CISHandler`
    so results are propagated and returns the updated `AtlasDataset`.

See [Running Modules](running-modules.md) for the full execution guide.

## Module Lifecycle

The `run()` method executes these standard steps:

1. **Import Parameters**: Load module-specific parameters (inherits from `AbstractModuleParameters`)
2. **Import Data**: Convert `AtlasDataset` to module-specific input dataset
3. **Validate**: Perform data validation (typically timestep consistency checks)
4. **Execute**: Run the module's core logic
5. **Validate Results**: Check output validity
6. **Export**: Update business model objects with results (if `export_result=True`)

Results are stored directly in the business model objects.

## AbstractModule Methods

All modules implement these core methods:

- `get_parameters_class()`: Returns the module's parameter class
- `import_data()`: Creates module-specific input dataset from AtlasDataset
- `validate_data()`: Validates input data consistency
- `execute()`: Runs the module's core logic
- `validates_results()`: Validates output data
- `export_results()`: Updates business model objects with results

## Key Design Patterns

**Module Pattern**: Consistent lifecycle across all modules

**Pydantic Models**: Parameters and datasets validated via Pydantic

**Business Model Integration**: Results stored directly in business objects

**Solver Interface**: Optimization modules use ATLAS `OptimisationModel` for solver abstraction

## See Also

- [Common Parameters](common-parameters.md): Parameters shared across modules
- [Running Modules](running-modules.md): Execution details and best practices
