class Order:
    equipment: str # Class Business model Equipment
    market_area: str # Class Business model MarketArea
    portfolio: str # Class Business model Portfolio
    accepted_power: float
    execution_date: str # Validation for date ?
    start_date: str # Validation for date ?
    end_date: str # Validation for date ?
    individual_spread: float
    is_agent_tso: bool
    order_type: str # possibles values : Buy, Sell
    price: float
    price_group: int
    product: str # possibles values : Intraday, DayAhead, AFRRUpProcurement, FRRDownProcurement, MFRRUpProcurement,
    # MFRRDownProcurement, RRUpProcurement, RRDownProcurement, AFRRActivation, MFRRActivation, RRActivation,
    # FCRActivation, FCRUpProcurement, FCRDownProcurement
    q_max: float
    q_min: float
