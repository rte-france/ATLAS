# AtlasDataset Usage Example

The `AtlasDataset` is the main data container in Atlas that stores and provides access to all business model objects.

## Loading a Dataset

```python
from atlas.io_utils.atlas_dataset import AtlasDataset

# Load dataset from directory
dataset = AtlasDataset.from_directory("data/atlas-dataset/portfolio-optimisation")
```

## Accessing Objects

```python
# Get all objects of a type
hydro_units = dataset.hydro.all()
# or
hydro_units = dataset.get_items_by_type('hydro')

# Get specific object by name
hydro = dataset.get("hydro", "my_hydro_plant")
# or
hydro = dataset.hydro.get("my_hydro_plant")

# Iterate over objects
for equipment in dataset.iter_by_types('hydro', 'thermal'):
    print(f"Equipment: {equipment.name}")
```

## Exporting Data

```python
# Export to directory
dataset.to_directory("output/atlas-dataset")

# Export to pickle
dataset.to_pickle("output/dataset.pkl")

# Export to python dictionnary
dataset.to_dict()

# Load from pickle
dataset = AtlasDataset.from_pickle("output/dataset.pkl")
```

## Creating a Custom Dataset

```python
from atlas.objects.node import Node
from atlas.objects.portfolio import Portfolio

# Create objects
node1 = Node(name="node_1")
node2 = Node(name="node_2")

portfolio_fr = Portfolio(name="fr")
portfolio_es = Portfolio(name="es")

# Create dataset
dataset = AtlasDataset(node=[node1, node2], portfolio=[portfolio_fr, portfolio_es])
```

For more information, see the [API Reference](../api/io/atlas_dataset.md).
