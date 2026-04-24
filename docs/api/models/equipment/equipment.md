# Equipment

Base class for all generation and consumption assets. Never instantiated directly — use a concrete subclass (`Thermal`, `Hydro`, `Solar`, `Wind`, `Storage`, `Load`, `OtherNonDispatchable`).

Every `Equipment` holds a reference to a [Node](../network/node.md) (physical location) and a [Portfolio](../market_operator/portfolio.md) (market operator).

::: atlas.Equipment
    options:
        show_if_no_docstring: false
        filters:
            - "!^_"
            - "!serializer"
            - "!^parse_"
            - "!^validate_"
