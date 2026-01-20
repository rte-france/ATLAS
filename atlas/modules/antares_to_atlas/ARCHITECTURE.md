# Antares to Atlas Converter - Architecture

## Design Goals

1. **Reusability**: Share converters across different Antares versions and hypotheses
2. **Scalability**: Easy to add new converters for new versions or hypotheses
3. **Maintainability**: Each converter is isolated and independently testable
4. **Flexibility**: Run all, standard only, specific only, or cherry-pick conversion steps
5. **Type Safety**: Pydantic-based parameter validation
6. **Gradual Migration**: Wrap legacy code first, refactor later

## Architecture Pattern

The converter uses the **Strategy Pattern** with a **Registry** system:

```
┌─────────────────────────────────────────────────────────────┐
│                    AntaresToAtlas                           │
│                   (Main Orchestrator)                       │
│                                                             │
│  - Loads parameters (Pydantic)                             │
│  - Builds converter registry                               │
│  - Creates conversion context                              │
│  - Executes all registered converters                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   ConverterRegistry                         │
│                                                             │
│  - Maintains lists of standard and specific converters     │
│  - Executes converters in order                            │
│  - Handles conditional execution                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ├─────────────────┬───────────────┐
                            ▼                 ▼               ▼
                    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                    │   Standard   │  │   Standard   │  │   Specific   │
                    │  Converter   │  │  Converter   │  │  Converter   │
                    │      A       │  │      B       │  │      C       │
                    └──────────────┘  └──────────────┘  └──────────────┘
```

## Class Hierarchy

```
BaseConverter (ABC)
│
├── StandardConverter
│   ├── NodeConverter
│   ├── LoadConverter
│   ├── WindConverter
│   ├── PVConverter
│   ├── HydroConverter
│   ├── LinkConverter
│   ├── ThermalConverter
│   └── NonDispatchableConverter
│
└── SpecificConverter
    ├── BP23 Converters
    │   ├── MixedFuelConverterBP23
    │   ├── ElectricVehicleConverterBP23
    │   ├── BatteryConverterBP23
    │   ├── DSRConverterBP23
    │   ├── PHSConverterBP23
    │   ├── WaterValueConverterBP23
    │   ├── InitialLevelConverterBP23
    │   └── NuclearModulationConverterBP23
    │
    └── BP24 Converters (future)
        └── ...
```
