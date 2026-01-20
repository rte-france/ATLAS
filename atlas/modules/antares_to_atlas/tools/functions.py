import API

# Specific conversion functions
# =============================


# Function used to find the binding constraints associated with an Antares Link instance
def find_binding_constraint_phs(antares_dataset, antares_link):
    for binding_constraint in antares_dataset.BindingConstraint.GetAllInstances():
        if antares_link in binding_constraint.LinkList:
            return binding_constraint

    API.IO.Trace.Log(f"WARNING for PHS {str(antares_link.Name)}, binding constraint not found", API.IO.LogTypeWarn)

    return 0


def node_special_format(node):
    thermal_name = ""

    if node == "dke":
        thermal_name = "DKe"

    elif node == "dkw":
        thermal_name = "DKw"

    elif node == "itca":
        thermal_name = "ITca"

    elif node == "itcn":
        thermal_name = "ITcn"

    elif node == "itcs":
        thermal_name = "ITcs"

    elif node == "itn":
        thermal_name = "ITn"

    elif node == "its":
        thermal_name = "ITs"

    elif node == "itsar":
        thermal_name = "ITsar"

    elif node == "itsic":
        thermal_name = "ITsic"

    elif node == "nom":
        thermal_name = "NOm"

    elif node == "non":
        thermal_name = "NOn"

    elif node == "nos":
        thermal_name = "NOs"

    elif node == "ukgb":
        thermal_name = "UKgb"

    elif node == "ukni":
        thermal_name = "UKni"

    # basic cases
    else:
        thermal_name = node.upper()

    return thermal_name
