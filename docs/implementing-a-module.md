# Implementing a New Module

This guide walks through creating a new ATLAS market module from scratch. Before reading this, familiarise yourself with the [Module Pattern](modules/module-pattern.md) and [Common Parameters](modules/common-parameters.md).

## File Structure

Create a directory under `atlas/modules/` with four files:

```
atlas/modules/my_module/
    __init__.py
    parameters.py      # Input parameters (Pydantic)
    input_dataset.py   # Data imported from AtlasDataset
    output_dataset.py  # Results + ChangeSets
    module.py          # Core logic
```

---

## Step 1 — Parameters

Extend `AbstractModuleParameters` and declare module-specific fields as Pydantic attributes.
`temporal`, `solver`, `output`, and `multiprocessing` are inherited automatically.

```python
# parameters.py
from pydantic import Field
from atlas.abstract_class.parameters import AbstractModuleParameters


class MyModuleParameters(AbstractModuleParameters):
    my_threshold: float = Field(
        default=100.0,
        description="Threshold used during execution.",
        gt=0,
    )
```

See [Common Parameters](modules/common-parameters.md) for the inherited fields.

---

## Step 2 — InputDataset

Extend `AbstractDataset` and extract the business objects your module needs from the `AtlasDataset`.
The constructor receives both the raw dataset and the parsed parameters.

```python
# input_dataset.py
from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.objects.market.market_area import MarketArea

from atlas.modules.my_module.parameters import MyModuleParameters


class MyModuleInputDataset(AbstractDataset[MyModuleParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: MyModuleParameters):
        self.parameters = parameters
        self.market_areas: list[MarketArea] = input_data.market_area.all()
```

Use module-specific wrapper objects (in an `input_objects/` sub-directory) when you need to
add computed properties or restrict the interface of a business object.

---

## Step 3 — OutputDataset

Extend `AbstractModuleOutput` and implement `build_change_sets()`.
Change sets tell the orchestrator what was modified so it can propagate results downstream.

```python
# output_dataset.py
from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.modules.my_module.input_dataset import MyModuleInputDataset
from atlas.modules.my_module.parameters import MyModuleParameters
from atlas.orchestrator.change_set import UpdateObject


class MyModuleOutputDataset(AbstractModuleOutput[MyModuleParameters]):
    def __init__(self, input_dataset: MyModuleInputDataset):
        self.market_areas = input_dataset.market_areas  # mutated during execute()

    def build_change_sets(self) -> None:
        for area in self.market_areas:
            self.change_sets.append(
                UpdateObject(
                    {"name": area.name, "my_result_field": area.my_result_field},
                    type(area),
                )
            )
```

Three change set types are available: `AddObject`, `UpdateObject`, `DeleteObject`.
All require a `"name"` key in the data dict.

---

## Step 4 — Module

Extend `AbstractModule` and implement the six required methods.

```python
# module.py
from atlas.abstract_class.module import AbstractModule
from atlas.io_utils.atlas_dataset import AtlasDataset

from atlas.modules.my_module.input_dataset import MyModuleInputDataset
from atlas.modules.my_module.output_dataset import MyModuleOutputDataset
from atlas.modules.my_module.parameters import MyModuleParameters


class MyModule(
    AbstractModule[MyModuleParameters, MyModuleInputDataset, MyModuleOutputDataset]
):
    def get_parameters_class(self) -> type[MyModuleParameters]:
        return MyModuleParameters

    def import_data(
        self, input_data: AtlasDataset, parameters: MyModuleParameters
    ) -> MyModuleInputDataset:
        return MyModuleInputDataset(input_data, parameters)

    def validate_data(
        self, parameters: MyModuleParameters, input_dataset: MyModuleInputDataset
    ) -> bool:
        return len(input_dataset.market_areas) > 0

    def execute(
        self, parameters: MyModuleParameters, input_dataset: MyModuleInputDataset
    ) -> MyModuleOutputDataset:
        output = MyModuleOutputDataset(input_dataset)

        for area in output.market_areas:
            area.my_result_field = self._compute(area, parameters)

        return output

    def validates_results(
        self,
        parameters: MyModuleParameters,
        input_dataset: MyModuleInputDataset,
        output_dataset: MyModuleOutputDataset,
    ) -> bool:
        return all(area.my_result_field is not None for area in output_dataset.market_areas)

    def export_results(
        self,
        parameters: MyModuleParameters,
        input_dataset: MyModuleInputDataset,
        output_dataset: MyModuleOutputDataset,
    ) -> None:
        # Write results back to the original business objects when export_result=True.
        # Leave empty if the module only populates ChangeSets.
        pass
```

### Method responsibilities

| Method | Must return | Raises if |
|---|---|---|
| `get_parameters_class` | the Parameters class | — |
| `import_data` | populated `InputDataset` | — |
| `validate_data` | `True` / `False` | `AssertionError` on `False` |
| `execute` | populated `OutputDataset` | — |
| `validates_results` | `True` / `False` | `AssertionError` on `False` |
| `export_results` | `None` | — |

---

## Step 5 — Registration

Expose the module in `atlas/__init__.py` so users can import it directly:

```python
# atlas/__init__.py
from atlas.modules.my_module.module import MyModule

__all__ = [
    ...,
    "MyModule",
]
```

---

## Step 6 — Module Registry

Add the module to `ModuleRegistry` so it is accessible via the CLI (`--module` flag) and `ModuleRun`:

```python
# atlas/orchestrator/module_registry.py
from atlas.modules.my_module.module import MyModule

class ModuleRegistry(Enum):
    ...
    MyModule = MyModule
```

The enum key is the name users pass to `atlas run --module MyModule`.

---

## Documentation Checklist

Follow the structure of existing modules under `docs/modules/`:

```
docs/modules/my-module/
    index.md                       # Overview and links
    user-guide/
        overview.md                # What the module does
        input-data.md              # Module-specific parameters
        running.md                 # Quick-start snippet
    developer/
        architecture.md            # Classes, data flow, design decisions
```

See [Running](modules/running-modules.md) for the expected content of `running.md`,
and any existing module's `developer/architecture.md` for the expected level of detail.
