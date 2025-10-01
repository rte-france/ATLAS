from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset


class PriceGroup:
    def __init__(self, id: int, time_index: int):
        self.id = id
        self.time_index = time_index
        self.market_area_names = []
        self.max_price = float("inf")
        self.min_price = -float("inf")
        min_rejected_sale = None
        max_rejected_buy = None