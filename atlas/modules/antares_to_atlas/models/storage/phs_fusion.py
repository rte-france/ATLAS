import API


def fusion(atlas_output_marker, L_closed, L_open, p):
    """
    Function making a fusion between phs created from open loop and closed loop
    nodes from Antares.
    It takes the following inputs:
    - 'atlas_output_marker': ATLAS output marker
    - 'L_closed': List of nodes that contain a closed loop phs
    - 'L_open': List of nodes that contain a open loop phs
    """

    if p.verbose:
        API.IO.Trace.Log("List of open PHS during fusion stage: {}".format(L_open))
        API.IO.Trace.Log("List of closed PHS during fusion stage: {}".format(L_closed))

    for node_name in L_open:
        if node_name in L_closed:
            # Fuse this open phs with the corresponding closed phs equipment
            closed_name = "{}_phs".format(node_name)
            closed_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(closed_name)

            open_name = "{}_phs_open".format(node_name)
            open_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(open_name)

            # fusion of power features
            closed_phs.MaximumPower += open_phs.MaximumPower
            closed_phs.MinimumPower += open_phs.MinimumPower
            closed_phs.MaximumEnergy += open_phs.MaximumEnergy

            atlas_output_marker.Equipment.Storage.DeleteInstanceByName(open_name)
        else:
            # If there is no closed phs equipment, simply rename the open one as "node_phs"
            open_name = "{}_phs_open".format(node_name)

            open_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(open_name)
            open_phs.SetPropertyByName("Name", "{}_phs".format(node_name))
            L_closed.append(node_name)

    return 0
