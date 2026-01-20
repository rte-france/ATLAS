import API


def conversion_node(antares_dataset, atlas_dataset, p):
    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            if p.verbose:
                msg = f"Creating Node {antares_node.Name}"
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            atlas_marketarea = atlas_dataset.Market.MarketArea.CreateInstance(antares_node.Name)
            atlas_ctrl_block = atlas_dataset.NetworkOperator.ControlBlock.CreateInstance(antares_node.Name)
            atlas_node = atlas_dataset.Network.Node.CreateInstance(antares_node.Name)
            atlas_marketarea.ControlBlock = atlas_ctrl_block
            atlas_node.MarketArea = atlas_marketarea
            atlas_node.ControlBlock = atlas_ctrl_block

            if p.consumption_production_separation:
                portfolio_gen = atlas_dataset.MarketAgent.Portfolio.CreateInstance(f"generator_{antares_node.Name}")
                portfolio_gen.MarketArea = atlas_marketarea
                portfolio_gen.ControlBlock = atlas_ctrl_block
                portfolio_load = atlas_dataset.MarketAgent.Portfolio.CreateInstance(f"supplier_{antares_node.Name}")
                portfolio_load.MarketArea = atlas_marketarea
                portfolio_load.ControlBlock = atlas_ctrl_block
            else:
                atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.CreateInstance(f"portfolio_{antares_node.Name}")
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
