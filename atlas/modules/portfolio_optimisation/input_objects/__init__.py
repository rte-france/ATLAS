from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO

EquipmentPO = HydroPO | LoadPO | WindPO | SolarPO | StoragePO | ThermalPO | OtherNonDispatchablePO
