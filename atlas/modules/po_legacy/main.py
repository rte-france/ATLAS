# coding: utf-8

from PO_solver import OptimalPlacement
import API
from parameters_file import Parameters


def main():
    # ------ Markers and Parameters
    input_marker = API.IO.GetInputMarkerByIdentifier("PO_input_marker")
    API.IO.SetOutputMarkerByIdentifier("PO_output_marker", input_marker)
    output_marker = API.IO.GetOutputMarkerByIdentifier("PO_output_marker")

    p = Parameters(output_marker)

    if p.verbose:
        API.IO.Trace.Log(str(p), API.IO.LogTypeInfo)

        msg = "Action starts ..."
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    OptimalPlacement(output_marker, p)

    if p.verbose:
        msg = "Action ends ..."
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)


main()
