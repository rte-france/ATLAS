class PriceGroup:
    def __init__(self, id: int, time_index: int):
        self.id = id
        self.time_index = time_index
        self.market_area_names = []
        self.max_price = float("inf")
        self.min_price = -float("inf")
