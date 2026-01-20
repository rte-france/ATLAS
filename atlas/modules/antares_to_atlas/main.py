import API
import battery
import dsr
import electric_vehicle
import hydraulic
import initial_level
import link

# Internal import
import load
import mixed_fuel
import multi_energy
import node
import nuclear_modulation
import other_non_dispatchable
import p2g_main
import particular_mid_peak
import phs_closed
import phs_fusion
import phs_open
import pv
import thermal
import water_value
import wind
from parameters_file import Parameters

# Reading input and output markers
# ================================

antares_dataset = API.IO.GetInputMarkerByIdentifier("antares_input")
atlas_dataset = API.IO.GetOutputMarkerByIdentifier("atlas_output")

# Managing File parameters
# ==================

p = Parameters()
if p.verbose:
    API.IO.Trace.Log(str(p), API.IO.LogTypeInfo)

# Converting Antares data into ATLAS
# ==================================
API.IO.Trace.Log("===================", API.IO.LogTypeInfo)
API.IO.Trace.Log("Standard Conversion", API.IO.LogTypeInfo)
API.IO.Trace.Log("===================", API.IO.LogTypeInfo)

# Creation of Nodes, MarketAreas, Portfolios and ControlBlocks
API.IO.Trace.Log("*** Node, MarketArea, Portfolio and ControlBlock Conversion ***", API.IO.LogTypeInfo)
node.conversion_node(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** Load Conversion ***", API.IO.LogTypeInfo)
load.conversion_load(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** Wind Conversion ***", API.IO.LogTypeInfo)
wind.conversion_wind(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** PV Conversion ***", API.IO.LogTypeInfo)
pv.conversion_pv(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** Hydro Conversion ***", API.IO.LogTypeInfo)
inflows_dictionary, hydro_reservoirs = hydraulic.conversion_hydraulic(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** Link Conversion ***", API.IO.LogTypeInfo)
link.conversion_link(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** Thermic Conversion ***", API.IO.LogTypeInfo)
thermic_parameter, thermic_properties = thermal.conversion_thermal(antares_dataset, atlas_dataset, p)

API.IO.Trace.Log("*** Non-dispatchable Conversion ***", API.IO.LogTypeInfo)
other_non_dispatchable.conversion_non_dispatchable(antares_dataset, atlas_dataset, p)

# Specific conversion
# ===================
API.IO.Trace.Log("===================")
API.IO.Trace.Log("Specific Conversion")
API.IO.Trace.Log("===================")

# Mixed Fuel
API.IO.Trace.Log("*** Mixed Fuel Conversion ***")
mixed_fuel.add_mixed_fuel(antares_dataset, atlas_dataset, thermic_parameter, thermic_properties, p)

# EV
API.IO.Trace.Log("*** Electric Vehicle Conversion ***")
electric_vehicle.convert_electric_vehicle(antares_dataset, atlas_dataset, p)

# Pcompmid and Pcomppeak
API.IO.Trace.Log("*** Specific Gas Units Conversion ***")
particular_mid_peak.pcomp_mid(antares_dataset, atlas_dataset, p)
particular_mid_peak.pcomp_peak(antares_dataset, atlas_dataset, p)

# PowerToGas
API.IO.Trace.Log("*** Power To Gas Conversion ***")
p2g_main.P2G(antares_dataset, atlas_dataset, p)
# This should be called after all thermic units are created
if p.use_multi_energy:
    multi_energy.update_variable_cost_unit_using_gas(antares_dataset, atlas_dataset, p)

# Battery
API.IO.Trace.Log("*** Battery Conversion ***")
battery.creation_battery(antares_dataset, atlas_dataset, p)

# DSR
API.IO.Trace.Log("*** Demand Side Response Conversion ***")
if "fr" in p.market_areas_list:
    dsr.dsr_fr(antares_dataset, atlas_dataset, p)
dsr.dsr_other_countries(antares_dataset, atlas_dataset, p)


# PumpedHydraulicStorage
API.IO.Trace.Log("*** Pumped Hydraulic Storage Conversion ***")

# PHS closed
closed_phs_list = phs_closed.creation_phs_closed(antares_dataset, atlas_dataset, hydro_reservoirs, p)

# PHS open
open_phs_list, inflows_dictionary = phs_open.creation_phs_open(
    antares_dataset, atlas_dataset, hydro_reservoirs, inflows_dictionary, p
)

if "fr" in p.market_areas_list:
    open_phs_list = phs_open.creation_phs_open_fr(antares_dataset, atlas_dataset, hydro_reservoirs, open_phs_list, p)

# PHS Fusion
phs_fusion.fusion(atlas_dataset, closed_phs_list, open_phs_list, p)

# Water Values and InitialLevel computations
# This is done after the PHS conversion to take into account new inflows added, and new reservoir size
API.IO.Trace.Log("*** Water Values Computation ***")
if p.use_water_value:
    water_value.compute_water_value(antares_dataset, atlas_dataset, inflows_dictionary, p)

API.IO.Trace.Log("*** InitialLevel Computation ***")
initial_level.initial_level_computation(antares_dataset, atlas_dataset, p)

# Nuclear modulation
if "fr" in p.market_areas_list:
    API.IO.Trace.Log("*** Nuclear Modulation Conversion ***")
    nuclear_modulation.add_nuclear_modulation(antares_dataset, atlas_dataset, p)


API.IO.Trace.Log("*** End of Conversion ***")
