# coding: utf-8

import API


# Function converting P2G technology of an Antares study into ATLAS Equipments
def P2G(antares_input_marker, atlas_output_marker, p):
    for antares_node in antares_input_marker.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            link_P2G_base = antares_input_marker.Link.GetInstanceByName("{}_z_p2g_base".format(antares_node.Name))
            link_P2G_marg = antares_input_marker.Link.GetInstanceByName("{}_z_p2g_marg".format(antares_node.Name))
            link_P2G_methanation = antares_input_marker.Link.GetInstanceByName(
                "{}_z_p2g_methanation".format(antares_node.Name)
            )

            # Base
            if link_P2G_base and link_P2G_base.DirectTransferCapacity.GetTimeSeriesByName("1").Abs().Max() != 0:
                msg = "Creating a new base P2G load equipment in market area {}".format(antares_node.Name)
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                p2g_instance = atlas_output_marker.Equipment.Load.CreateInstance(
                    "{}_p2g_base".format(antares_node.Name)
                )

                # general properties
                if p.consumption_production_separation:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "supplier_{}".format(antares_node.Name)
                    )
                else:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "portfolio_{}".format(antares_node.Name)
                    )

                p2g_instance.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)
                p2g_instance.Portfolio = portfolio
                # In the study, the P2G_base is 100% fatal
                p2g_instance.LoadType = "OtherNonDispatchableLoad"

                # MaximumPowerForecast
                p2g_instance.MaximumPowerForecast.AddTimeSeries(
                    p.execution_date, -1.0 * link_P2G_base.DirectTransferCapacity.GetTimeSeriesByName("1")
                )

                # VariableCost
                # In BP23, p2g_base is a fatalband, hence no need for the TS
                # variable_cost = antares_input_marker.ThermalTechnology.GetInstanceByName("z_P2G_base").MarketBidCost
                # p2g_instance.VariableCost = API.TimeSeries.NewTimeSeries('MarketBid', API.TimeSeries.Constant, p.start_date.ToString(), '1Y', 2, variable_cost, '')

            # Marg
            if link_P2G_marg and link_P2G_marg.DirectTransferCapacity.GetTimeSeriesByName("1").Abs().Max() != 0:
                msg = "Creating a new marginal P2G load equipment in market area {}".format(antares_node.Name)
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                p2g_instance = atlas_output_marker.Equipment.Load.CreateInstance(
                    "{}_p2g_marg".format(antares_node.Name)
                )

                # general properties
                if p.consumption_production_separation:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "supplier_{}".format(antares_node.Name)
                    )
                else:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "portfolio_{}".format(antares_node.Name)
                    )

                p2g_instance.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)
                p2g_instance.Portfolio = portfolio
                p2g_instance.LoadType = "PowerToGas"

                # MaximumPowerForecast
                p2g_instance.MaximumPowerForecast.AddTimeSeries(
                    p.execution_date, -1.0 * link_P2G_marg.DirectTransferCapacity.GetTimeSeriesByName("1")
                )

                # VariableCost
                variable_cost = antares_input_marker.ThermalTechnology.GetInstanceByName(
                    "z_p2g_marg_z_P2G_marg_marg"
                ).MarketBidCost
                p2g_instance.VariableCost = API.TimeSeries.NewTimeSeries(
                    "MarketBid", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, variable_cost, ""
                )

            # Methanation
            if (
                link_P2G_methanation
                and link_P2G_methanation.DirectTransferCapacity.GetTimeSeriesByName("1").Abs().Max() != 0
            ):
                msg = "Creating a new methanation P2G load equipment in market area {}".format(antares_node.Name)
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                p2g_instance = atlas_output_marker.Equipment.Load.CreateInstance(
                    "{}_p2g_methanation".format(antares_node.Name)
                )

                # general properties
                if p.consumption_production_separation:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "supplier_{}".format(antares_node.Name)
                    )
                else:
                    portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "portfolio_{}".format(antares_node.Name)
                    )

                p2g_instance.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)
                p2g_instance.Portfolio = portfolio
                p2g_instance.LoadType = "PowerToGas"

                # MaximumPowerForecast
                p2g_instance.MaximumPowerForecast.AddTimeSeries(
                    p.execution_date, -1.0 * link_P2G_methanation.DirectTransferCapacity.GetTimeSeriesByName("1")
                )

                # VariableCost
                variable_cost = antares_input_marker.ThermalTechnology.GetInstanceByName(
                    "z_p2g_methanation_z_P2G_methanation_methanation"
                ).MarketBidCost
                p2g_instance.VariableCost = API.TimeSeries.NewTimeSeries(
                    "MarketBid", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, variable_cost, ""
                )

            # ====================== effacements
            # Not considered in 2030 and 2050 studies
            """
            msg = "Creating thermic group of H2 and CH4 in the Node {}".format(antares_node.Name)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            thermic_h2 = atlas_output_marker.Equipment.Thermic.CreateInstance(antares_node.Name+"_"+functions.node_special_format(antares_node.Name)+"_v_me_h2")
            thermic_ch4 = atlas_output_marker.Equipment.Thermic.CreateInstance(antares_node.Name+"_"+functions.node_special_format(antares_node.Name)+"_v_me_ch4")

            #general properties
            if p.consumption_production_separation:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName("generator_"+antares_node.Name)
            else:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName("portfolio_"+antares_node.Name)

            thermic_h2.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)
            thermic_h2.Portfolio = portfolio

            thermic_ch4.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)
            thermic_ch4.Portfolio = portfolio

            #we give variable cost to these thermic group thanks to marginal price of nodes v_me_H2 and v_me_CH4 in the input marker
            #to multiply by yield

            #marginal price of nodes v_me_CH4 and v_me_H2
            v_me_h2 = antares_input_marker.Node.GetInstanceByName("v_me_h2")
            v_me_ch4 = antares_input_marker.Node.GetInstanceByName("v_me_ch4")

            #yields (<1)
            yield_h2 = yield_electrolysers_node(antares_input_marker, antares_node.Name)
            yield_ch4 = yield_methanation_node(antares_input_marker, antares_node.Name)

            #variable costs of output
            thermic_h2.VariableCost = v_me_h2.CalculatedMarginalPrice[str(p.scenario)] * yield_h2
            thermic_ch4.VariableCost = v_me_ch4.CalculatedMarginalPrice[str(p.scenario)] * yield_ch4
            """

    return 0


# Functions specific to electrolyseurs and methanation
def yield_electrolysers_node(antares_input_marker, node):
    # yield of thermal technology found in binding constraint
    bc_h2 = antares_input_marker.BindingConstraint.GetInstanceByName("me_p2g_base")
    if not bc_h2:
        API.IO.Trace.Log("WARNING during P2G conversion, binding constraint me_p2g_base not found", API.IO.LogTypeWarn)

    all_links = [link.Name for link in bc_h2.LinkList]
    link = "{}_z_p2g_base".format(node)

    # In Weights, linklist in pole position, then clusterlist (empty in our case)
    yield_electrolysers_node_result = bc_h2.Weights[all_links.index(link)]

    return yield_electrolysers_node_result


def yield_methanation_node(antares_input_marker, node):
    # yield of thermal technology found in binding constraint
    bc_ch4 = antares_input_marker.BindingConstraint.GetInstanceByName("me_p2g_methanation")
    if not bc_ch4:
        API.IO.Trace.Log(
            "WARNING during P2G conversion, binding constraint me_p2g_methanation not found", API.IO.LogTypeWarn
        )

    all_links = [link.Name for link in bc_ch4.LinkList]
    link = "{}_z_p2g_methanation".format(node)

    # In Weights, linklist in pole position, then clusterlist (empty in our case)
    yield_methanation_node_result = bc_ch4.Weights[all_links.index(link)]

    return yield_methanation_node_result
