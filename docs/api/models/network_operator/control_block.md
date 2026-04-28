# ControlBlock

Top-level operator entity representing a Transmission System Operator (TSO) control zone. Holds balancing needs, reserve procurement requirements, and imbalance settlement prices.

No dependency on other Atlas objects — always created first.

::: atlas.ControlBlock
    options:
        show_if_no_docstring: false
        filters:
            - "!^_"
            - "!serializer"
            - "!^parse_"
            - "!^validate_"
