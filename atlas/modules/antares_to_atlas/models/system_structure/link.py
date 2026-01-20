# Construct the MarketBorder objects based on the Link objects of the input marker
# Select only the Link between areas defined in the parameter MarketAreas
def conversion_link(antares_dataset, atlas_dataset, p):
    for links in antares_dataset.Link.GetAllInstances():
        if not (links.UphillNode.Name in p.market_areas_list and links.DownhillNode.Name in p.market_areas_list):
            continue
        if (
            links.DirectTransferCapacity.TimeSeries[0].Abs().Max() == 0.0
            and links.IndirectTransferCapacity.TimeSeries[0].Abs().Max() == 0.0
        ):
            continue

        mkt_border = atlas_dataset.Market.MarketBorder.CreateInstance(links.Name)
        node_1 = atlas_dataset.Market.MarketArea.GetInstanceByName(links.UphillNode.Name)
        node_2 = atlas_dataset.Market.MarketArea.GetInstanceByName(links.DownhillNode.Name)
        ctrl_block_1 = atlas_dataset.NetworkOperator.ControlBlock.GetInstanceByName(links.UphillNode.Name)
        ctrl_block_2 = atlas_dataset.NetworkOperator.ControlBlock.GetInstanceByName(links.DownhillNode.Name)
        mkt_border.UphillMarketArea = node_1
        mkt_border.DownhillMarketArea = node_2
        mkt_border.UphillControlBlock = ctrl_block_1
        mkt_border.DownhillControlBlock = ctrl_block_2
        mkt_border.MinimumFlow = -1.0 * links.IndirectTransferCapacity.TimeSeries[0]
        mkt_border.MaximumFlow = links.DirectTransferCapacity.TimeSeries[0]

    return None
