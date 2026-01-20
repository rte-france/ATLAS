import API


def conversion_node(antares_input_marker, atlas_output_marker, p):
    for antares_node in antares_input_marker.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            if p.verbose:
                msg = "Creating Node {}".format(antares_node.Name)
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            atlas_marketarea = atlas_output_marker.Market.MarketArea.CreateInstance(antares_node.Name)
            atlas_ctrl_block = atlas_output_marker.NetworkOperator.ControlBlock.CreateInstance(antares_node.Name)
            atlas_node = atlas_output_marker.Network.Node.CreateInstance(antares_node.Name)
            atlas_marketarea.ControlBlock = atlas_ctrl_block
            atlas_node.MarketArea = atlas_marketarea
            atlas_node.ControlBlock = atlas_ctrl_block

            if p.consumption_production_separation:
                portfolio_gen = atlas_output_marker.MarketAgent.Portfolio.CreateInstance(
                    "generator_{}".format(antares_node.Name)
                )
                portfolio_gen.MarketArea = atlas_marketarea
                portfolio_gen.ControlBlock = atlas_ctrl_block
                portfolio_load = atlas_output_marker.MarketAgent.Portfolio.CreateInstance(
                    "supplier_{}".format(antares_node.Name)
                )
                portfolio_load.MarketArea = atlas_marketarea
                portfolio_load.ControlBlock = atlas_ctrl_block
            else:
                atlas_portfolio = atlas_output_marker.MarketAgent.Portfolio.CreateInstance(
                    "portfolio_{}".format(antares_node.Name)
                )
                atlas_portfolio.MarketArea = atlas_marketarea
                atlas_portfolio.ControlBlock = atlas_ctrl_block

            if str(p.scenario) in antares_node.CalculatedMarginalPrice.Index:
                atlas_marketarea.PriceForecastMedium.AddTimeSeries(
                    p.execution_date, antares_node.CalculatedMarginalPrice.GetTimeSeriesByName(str(p.scenario))
                )
            atlas_marketarea.MinimumPrice = API.TimeSeries.NewTimeSeries(
                "MinimumPrice", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, p.minimum_price, "MW"
            )
            atlas_marketarea.MaximumPrice = API.TimeSeries.NewTimeSeries(
                "MaximumPrice", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, p.maximum_price, "MW"
            )

    return None
