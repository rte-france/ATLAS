# Eager/Lazy Architecture for Math Objects

## Overview

This document describes the architectural pattern for `Timeseries`/`LazyTimeseries` and `Matrix`/`LazyMatrix` objects in ATLAS.

**Goals**:
1. Share common methods between eager and lazy implementations
2. Provide proper typing through abstract base classes
3. Clearly distinguish when lazy operations collect data
4. Minimize code duplication

## Problem Statement

Currently, `Timeseries` and `LazyTimeseries` (and their Matrix equivalents) have:
- Duplicate code for similar operations
- No shared type interface
- Unclear semantics around when lazy operations collect data
- Incomplete method parity

## Architectural Design

### 1. Method Categories

#### Green Zone: Lazy-Preserving Methods
Work on both eager and lazy **without collecting**:
- `filter()`, `slice()`, `slice_with_offset()`
- `abs()`, `round()`
- Arithmetic operations (`__add__`, `__mul__`, etc.)

#### Yellow Zone: Collection Methods
Explicitly collect data and return **scalar results**:
- `max()`, `min()`, `sum()`
- `get_value()`, `first_date()`, `last_date()`
- `__len__`, `__contains__`

For lazy: Only the computed scalar is collected, not the full dataset.

#### Orange Zone: Collection-Required Methods
Require **full materialization**. Exist on both types:
- **For Timeseries**: Work normally (data already materialized)
- **For LazyTimeseries**: Collect data first (⚠️ warnings in docstrings)

Examples:
- **Resampling**: `set_frequency()`, `upsample()`, `groupby()`
- **Modification**: `set_value()`, `set_values()`, `add_index()`
- **I/O**: `to_file()`, `to_file_with_attribute()`

**For LazyTimeseries**, these methods:
1. Collect the lazy frame into memory
2. Perform operation on eager version
3. Convert back to lazy
4. Return LazyTimeseries (can continue chaining)

### 2. Design Pattern: Abstract Base Class

```
┌─────────────────────────────────────────────────────────┐
│             AbstractTimeseries (ABC)                        │
│                                                         │
│  Shared implementation (Green Zone):                   │
│  - filter(), slice(), abs(), round()                   │
│                                                         │
│  Abstract methods (Yellow Zone):                       │
│  - max(), min(), sum(), __len__()                      │
│  - first_date(), last_date()                           │
│                                                         │
│  Template methods:                                     │
│  - abstractmethod: _get_data() → df or lf              │
│  - abstractmethod: _return(data, inplace) → self or new  │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │ inherits
                ┌───────────┴───────────┐
                │                       │
┌───────────────────────┐   ┌───────────────────────┐
│   Timeseries          │   │   LazyTimeseries      │
│   (Eager)             │   │   (Lazy)              │
│                       │   │                       │
│ _get_data()           │   │ _get_data()           │
│   → DataFrame         │   │   → LazyFrame         │
│                       │   │                       │
│ _return()               │   │ _return()               │
│   → Timeseries        │   │   → LazyTimeseries    │
│                       │   │                       │
│ Orange Zone:          │   │ Orange Zone:          │
│ - set_frequency()     │   │ - set_frequency() ⚠️  │
│ - upsample()          │   │ - upsample() ⚠️       │
│ - groupby()           │   │ - groupby() ⚠️        │
│                       │   │                       │
│ + to_lazy()           │   │ + collect()           │
└───────────────────────┘   └───────────────────────┘
```

**Why This Design?**
1. **Simple**: Only 3 classes (AbstractTimeseries, Timeseries, LazyTimeseries)
2. **No duplication**: Shared logic in base class
3. **Clear hierarchy**: Single inheritance
4. **Pythonic**: Standard library ABC pattern
5. **Template Method**: Subclasses customize via `_get_data()` and `_return()`

### 3. Implementation Example

#### Abstract Base Class

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Self
import polars as pl

TBackend = TypeVar('TBackend', pl.DataFrame, pl.LazyFrame)

class AbstractTimeseries(ABC, Generic[TBackend]):
    timezone: str

    @abstractmethod
    def _get_data(self) -> TBackend:
        """Return DataFrame or LazyFrame."""
        pass

    @abstractmethod
    def _return(self, data: TBackend, inplace: bool) -> Self:
        """return data into appropriate type."""
        pass

    # Green Zone: Shared implementation
    def filter(self, item, date_format="YYYY-MM-DD HH:mm:ss", inplace=True) -> Self:
        backend = self._get_data()
        # ... filtering logic works on both DataFrame and LazyFrame
        filtered = backend.filter(...)
        return self._return(filtered, inplace)

    def abs(self, inplace=True) -> Self:
        backend = self._get_data()
        result = backend.with_columns(pl.col("value").abs())
        return self._return(result, inplace)

    # Yellow Zone: Abstract (different implementations)
    @abstractmethod
    def max(self) -> float:
        pass

    @abstractmethod
    def min(self) -> float:
        pass
```

#### Eager Implementation

```python
class Timeseries(AbstractTimeseries[pl.DataFrame]):
    def __init__(self, timeseries, timezone="UTC"):
        self.timeseries: pl.DataFrame = ...
        self.timezone = timezone

    def _get_data(self) -> pl.DataFrame:
        return self.timeseries

    def _return(self, data: pl.DataFrame, inplace: bool) -> Timeseries:
        if inplace:
            self.timeseries = data.sort("time")
            return self
        return Timeseries(data, self.timezone)

    # Yellow Zone: Trivial (already collected)
    def max(self) -> float:
        return self.timeseries["value"].max()

    # Orange Zone: Works normally
    def set_frequency(self, frequency, inplace=True) -> Timeseries:
        # Existing implementation
        ...

    def to_lazy(self) -> LazyTimeseries:
        return LazyTimeseries(self.timeseries.lazy(), self.timezone)
```

#### Lazy Implementation

```python
class LazyTimeseries(AbstractTimeseries[pl.LazyFrame]):
    def __init__(self, timeseries, timezone="UTC"):
        self.timeseries: pl.LazyFrame = ...
        self.timezone = timezone

    def _get_data(self) -> pl.LazyFrame:
        return self.timeseries

    def _return(self, data: pl.LazyFrame, inplace: bool) -> LazyTimeseries:
        if inplace:
            self.timeseries = data.sort("time")
            return self
        return LazyTimeseries(data.sort("time"), self.timezone)

    # Yellow Zone: Collect only scalar
    def max(self) -> float:
        return self.timeseries.select(pl.col("value").max()).collect().item()

    # Orange Zone: Collect, transform, convert back
    def set_frequency(self, frequency, inplace=True) -> LazyTimeseries:
        """⚠️ WARNING: Materializes all data into memory."""
        eager = self.collect()
        resampled = eager.set_frequency(frequency, inplace=False)
        if inplace:
            self.timeseries = resampled.to_lazy().timeseries
            return self
        return resampled.to_lazy()

    def upsample(self, frequency, interpolation_method="constant", inplace=True) -> LazyTimeseries:
        """⚠️ WARNING: Materializes all data into memory."""
        eager = self.collect()
        upsampled = eager.upsample(frequency, interpolation_method, inplace=False)
        if inplace:
            self.timeseries = upsampled.to_lazy().timeseries
            return self
        return upsampled.to_lazy()

    def collect(self) -> Timeseries:
        return Timeseries(self.timeseries.collect(), self.timezone)
```

### 4. Usage Patterns

#### Working with Lazy Data

```python
lazy_ts = LazyTimeseries.from_file("large_dataset.parquet")

# Chain lazy operations (no collection)
result = (lazy_ts
    .filter(["2024-01-01", "2024-01-02"])  # Lazy
    .abs()                                  # Lazy
    .round(2))                              # Lazy

# Collect only scalars
max_value = result.max()  # Efficient

# Orange Zone operations collect
resampled = result.set_frequency("1h")  # ⚠️ Collects
filtered_again = resampled.filter(...)   # Back to lazy
```

#### Working with Eager Data

```python
ts = Timeseries.from_file("dataset.csv")

ts.filter(..., inplace=True)
ts.set_frequency("1h", inplace=True)  # No collection needed
ts.set_value("2024-01-01 12:00:00", 42.0)
```


## Summary

### Key Design Decisions

1. **ABC pattern**: Simpler than mixins, fewer objects, standard Python
2. **Orange Zone on both types**: `set_frequency()`, `upsample()`, `groupby()` exist on both with clear warnings
3. **Four zones**: Green (lazy-preserving), Yellow (scalars), Orange (full collection), Red (avoid)
4. **Template Method**: `_get_data()` and `_return()` customize behavior


### Architecture Benefits

✓ **Shared methods** through ABC

✓ **Minimal objects**: Only 3 classes

✓ **No duplication**: Single implementation of shared logic

✓ **Clear semantics**: Warnings document collection points

✓ **Consistent API**: Both types have same methods

✓ **Performance**: Lazy chains stay lazy, explicit collection when needed

### Applies To

- `AbstractTimeseries` → `Timeseries` + `LazyTimeseries`
- `AbstractScenarioMatrix` → (`ScenarioMatrix` → `ForecastinMatrix`) + (`LazyScenarioMatrix` → `LazyForecastingMatrix`)
