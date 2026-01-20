import API


def fusion(atlas_dataset, L_closed, L_open, p):
    """
    Function making a fusion between phs created from open loop and closed loop
    nodes from Antares.
    It takes the following inputs:
    - 'atlas_dataset': ATLAS output marker
    - 'L_closed': List of nodes that contain a closed loop phs
    - 'L_open': List of nodes that contain a open loop phs
    """

    if p.verbose:
        API.IO.Trace.Log(f"List of open PHS during fusion stage: {L_open}")
        API.IO.Trace.Log(f"List of closed PHS during fusion stage: {L_closed}")

    for node_name in L_open:
        if node_name in L_closed:
            # Fuse this open phs with the corresponding closed phs equipment
            closed_name = f"{node_name}_phs"
            closed_phs = atlas_dataset.Equipment.Storage.GetInstanceByName(closed_name)

            open_name = f"{node_name}_phs_open"
            open_phs = atlas_dataset.Equipment.Storage.GetInstanceByName(open_name)

            # fusion of power features
            closed_phs.MaximumPower += open_phs.MaximumPower
            closed_phs.MinimumPower += open_phs.MinimumPower
            closed_phs.MaximumEnergy += open_phs.MaximumEnergy

            atlas_dataset.Equipment.Storage.DeleteInstanceByName(open_name)
        else:
            # If there is no closed phs equipment, simply rename the open one as "node_phs"
            open_name = f"{node_name}_phs_open"

            open_phs = atlas_dataset.Equipment.Storage.GetInstanceByName(open_name)
            open_phs.SetPropertyByName("Name", f"{node_name}_phs")
            L_closed.append(node_name)

    return 0
