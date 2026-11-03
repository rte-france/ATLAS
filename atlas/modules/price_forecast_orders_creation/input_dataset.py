from atlas import AtlasDataset, OtherNonDispatchable
from atlas.abstract_class.dataset import AbstractDataset
from atlas.modules.price_forecast_orders_creation.input_objects.hydro import HydroPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.load import LoadPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.storage import StoragePFOC
from atlas.modules.price_forecast_orders_creation.input_objects.thermal import ThermalPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.wind import WindPFOC
from atlas.modules.price_forecast_orders_creation.parameters import PriceForecastOrdersCreationParameters


class PriceForecastOrdersCreationInputDataset(AbstractDataset[PriceForecastOrdersCreationParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: PriceForecastOrdersCreationParameters):
        self.parameters: PriceForecastOrdersCreationParameters = parameters
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_data.other_non_dispatchable.all()
        self.storage: list[StoragePFOC] = [StoragePFOC(**obj) for obj in input_data.storage]
        self.hydro: list[HydroPFOC] = [HydroPFOC(**obj) for obj in input_data.hydro]
        self.wind: list[WindPFOC] = [WindPFOC(**obj) for obj in input_data.wind]
        self.thermal: list[ThermalPFOC] = [ThermalPFOC(**obj) for obj in input_data.thermal]
        self.load: list[LoadPFOC] = [LoadPFOC(**obj) for obj in input_data.load]
