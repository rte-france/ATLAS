import API


# Function adding prices of h2 and ch4 to the VariableCost of thermic groups that use these gases as fuel
def update_variable_cost_unit_using_gas(antares_input_marker, atlas_output_marker, p):
    # for group using gas (h2 or ch4) we add prices of h2 and ch4 (calculated with yields) to thermic groups

    # marginal price of nodes v_me_CH4 and v_me_H2
    marginal_price_h2 = antares_input_marker.Node.GetInstanceByName("v_me_h2").CalculatedMarginalPrice[str(p.scenario)]
    marginal_price_ch4 = antares_input_marker.Node.GetInstanceByName("v_me_ch4").CalculatedMarginalPrice[
        str(p.scenario)
    ]

    # yield of electrolysis and methanation found in binding constraint
    bc_h2 = antares_input_marker.BindingConstraint.GetInstanceByName("me_prod_h2")
    if not bc_h2:
        API.IO.Trace.Log(
            "WARNING during multi energy conversion, binding constraint me_prod_h2 not found", API.IO.LogTypeWarn
        )

    bc_ch4 = antares_input_marker.BindingConstraint.GetInstanceByName("me_prod_ch4")
    if not bc_ch4:
        API.IO.Trace.Log(
            "WARNING during multi energy conversion, binding constraint me_prod_ch4 not found", API.IO.LogTypeWarn
        )

    list_clusterlist_h2 = [cluster.Name for cluster in bc_h2.ClusterList]
    list_clusterlist_ch4 = [cluster.Name for cluster in bc_ch4.ClusterList]

    # ch4
    for thermal in list_clusterlist_ch4:
        # if in clusterlist_ch4 means that the thermic group use ch4

        if atlas_output_marker.Equipment.Thermic.GetInstanceByName(thermal):
            # some thermal in bc are not in the marker areas chosen for example

            msg = "Adding variable cost CH4 to thermal : {}".format(thermal)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            # yield is already inversed (>1)
            yield_ch4 = bc_ch4.Weights[list_clusterlist_ch4.index(thermal)]

            # variable cost of thermal has to be modified with 1/yield * marginal price of ch4
            atlas_output_marker.Equipment.Thermic.GetInstanceByName(thermal).VariableCost = (
                marginal_price_ch4 * yield_ch4
            )

    # h2
    for thermal in list_clusterlist_h2:
        if atlas_output_marker.Equipment.Thermic.GetInstanceByName(thermal):
            # some thermal in bc are not in the marker areas chosen for example

            msg = "Adding variable cost H2 to thermal : {}".format(thermal)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            # yield is already inversed (>1)
            yield_h2 = bc_h2.Weights[list_clusterlist_h2.index(thermal)]

            # variable cost of thermal has to be modified with 1/yield * marginal price of h2
            atlas_output_marker.Equipment.Thermic.GetInstanceByName(thermal).VariableCost = marginal_price_h2 * yield_h2

    # TODO: Update VariableCost for P2G units in multi-energy
    # For p2g_marg :
    # H2Price = antares_input_marker.Node.GetInstanceByName("v_me_h2").CalculatedMarginalPrice[str(p.scenario)]
    # p2g_instance.VariableCost = H2Price * yield_electrolysers_node(antares_input_marker, antares_node.Name)
    # For p2g_meth
    # CH4Price = antares_input_marker.Node.GetInstanceByName("v_me_ch4").CalculatedMarginalPrice[str(p.scenario)]
    # p2g_instance.VariableCost = CH4Price * yield_methanation_node(antares_input_marker, antares_node.Name)
    # See p2g_main.py for the yield functions

    return 0
