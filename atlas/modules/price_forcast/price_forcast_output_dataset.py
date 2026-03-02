import copy

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.models.business_model import BusinessModel
from atlas.modules.price_forcast.data_models.load import LoadIDPF
from atlas.modules.price_forcast.data_models.market_area import MarketAreaIDPF
from atlas.modules.price_forcast.data_models.solar import SolarIDPF
from atlas.modules.price_forcast.data_models.wind import WindIDPF
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters


class PriceForcastOutputDataset(AbstractModuleOutput[PriceForcastParameters]):
    def build_change_sets(self) -> None:
        # FIXME
        pass

    def __init__(self, parameters: PriceForcastParameters, input_dataset: PriceForcastInputDataset):
        self.parameters: PriceForcastParameters = copy.deepcopy(parameters)
        self.input_data = input_dataset

        self.market_area: list[MarketAreaIDPF] = copy.deepcopy(input_dataset.market_area)
        self.load: list[LoadIDPF] = copy.deepcopy(input_dataset.load)
        self.solar: list[SolarIDPF] = copy.deepcopy(input_dataset.solar)
        self.wind: list[WindIDPF] = copy.deepcopy(input_dataset.wind)

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
