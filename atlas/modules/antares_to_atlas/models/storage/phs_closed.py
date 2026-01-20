# coding: utf-8

import API
import functions


# Function creating a PumpedHydraulicStorage Equipment based on an open PHS in the Antares input marker
def creation_phs_closed(antares_input_marker, atlas_output_marker, hydro_reservoirs, p):
    # Define a list storing all closed_phs equipemnts created
    closed_phs_list = []

    # First, find links pointing to turb virtual nodes and create the corresponding phs equipments
    for links in antares_input_marker.Link.GetAllInstances():
        if links.DownhillNode.Name == "x_closed_turb":
            # looking for the node name, and filter it according to market_areas_list
            node_name = links.UphillNode.Name

            if node_name not in p.market_areas_list:
                continue

            if (
                hydro_reservoirs[node_name]["ClosedLoopCapacity"] == 0.0
                or links.IndirectTransferCapacity.GetTimeSeriesByName("1").Abs().Max() == 0.0
            ):
                continue

            # we create the phs equipment in ATLAS
            msg = "Creating phs equipment in Node {}".format(node_name)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            instance_name = "{}_phs".format(node_name)
            atlas_output_marker.Equipment.Storage.CreateInstance(instance_name)

            closed_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(instance_name)

            binding_constraint = functions.find_binding_constraint_phs(antares_input_marker, links)

            if p.consumption_production_separation:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                    "generator_{}".format(node_name)
                )
            else:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                    "portfolio_{}".format(node_name)
                )

            # general properties of a storage equipment
            closed_phs.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
            closed_phs.Portfolio = portfolio
            closed_phs.StorageType = "PumpedHydraulicStorage"
            if binding_constraint:
                closed_phs.DischargeEfficiency = abs(binding_constraint.Weights[1])  # turb
                closed_phs.ChargeEfficiency = abs(binding_constraint.Weights[0])  # pump
            else:
                closed_phs.DischargeEfficiency = 1  # turb
                closed_phs.ChargeEfficiency = 1  # pump
            closed_phs.TransitionDuration = 0
            closed_phs.SetupDelay = 0

            # MaximumEnergy and MinimumStateOfCharge
            closed_phs.MaximumEnergy = API.TimeSeries.NewTimeSeries(
                "MaximumEnergy",
                API.TimeSeries.Constant,
                p.start_date.ToString(),
                "1Y",
                2,
                float(hydro_reservoirs[node_name]["ClosedLoopCapacity"]),
                "MWh",
            )

            closed_phs.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
                "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, ""
            )

            # Initial level
            closed_phs.StorageInitialLevel = p.phs_initial_level

            # specific properties for phs : Power, Pmax and Pmin
            # power
            power_timeseries = -1 * links.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))
            closed_phs.Power.AddTimeSeries(p.execution_date, power_timeseries)

            # Pmax
            closed_phs.MaximumPower = links.IndirectTransferCapacity.GetTimeSeriesByName("1")

            # Add closed_phs equipment to closed_phs_list
            closed_phs_list.append(node_name)

    # Then, find links pointing to pump virtual nodes and update the corresponding phs ATLAS equipments
    for links in antares_input_marker.Link.GetAllInstances():
        if links.DownhillNode.Name == "x_closed_pump":
            # looking for the node name, and filter it according to market_areas_list
            node_name = links.UphillNode.Name

            if node_name not in p.market_areas_list:
                continue

            if (
                hydro_reservoirs[node_name]["ClosedLoopCapacity"] == 0.0
                or links.DirectTransferCapacity.GetTimeSeriesByName("1").Abs().Max() == 0.0
            ):
                continue

            # Find the closed_phs equipment in the output marker, if it has been created before
            closed_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName("{}_phs".format(node_name))

            if not closed_phs:
                API.IO.Trace.Log(
                    "WARNING: No closed_phs was created with turb node for {}".format(node_name + "_phs"),
                    API.IO.LogTypeWarn,
                )

                msg = "Creating phs equipment in Node {}".format(node_name)
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                instance_name = "{}_phs".format(node_name)
                atlas_output_marker.Equipment.Storage.CreateInstance(instance_name)

                closed_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(instance_name)

                binding_constraint = functions.find_binding_constraint_phs(antares_input_marker, links)

                if p.consumption_production_separation:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "generator_{}".format(node_name)
                    )
                else:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "portfolio_{}".format(node_name)
                    )

                # general properties of a storage equipment
                closed_phs.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
                closed_phs.Portfolio = portfolio
                closed_phs.StorageType = "PumpedHydraulicStorage"
                if binding_constraint:
                    closed_phs.DischargeEfficiency = abs(binding_constraint.Weights[1])  # turb
                    closed_phs.ChargeEfficiency = abs(binding_constraint.Weights[0])  # pump
                else:
                    closed_phs.DischargeEfficiency = 1  # turb
                    closed_phs.ChargeEfficiency = 1  # pump
                closed_phs.TransitionDuration = 0
                closed_phs.SetupDelay = 0

                # MaximumEnergy and MinimumStateOfCharge
                closed_phs.MaximumEnergy = API.TimeSeries.NewTimeSeries(
                    "MaximumEnergy",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    float(hydro_reservoirs[node_name]["ClosedLoopCapacity"]),
                    "MWh",
                )

                closed_phs.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
                    "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, ""
                )

                # Initial level
                closed_phs.StorageInitialLevel = p.phs_initial_level

                # Add closed_phs equipment to closed_phs_list
                closed_phs_list.append(node_name)

            # Pmin
            closed_phs.MinimumPower = -1.0 * links.DirectTransferCapacity.GetTimeSeriesByName("1")

            # power
            power_timeseries = -1.0 * links.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))

            old_power = closed_phs.Power[str(p.execution_date)]

            if old_power:
                closed_phs.Power.DeleteTimeSeries(p.execution_date)
                closed_phs.Power.AddTimeSeries(p.execution_date, old_power + power_timeseries)

            else:
                closed_phs.Power.AddTimeSeries(p.execution_date, power_timeseries)

    return closed_phs_list
