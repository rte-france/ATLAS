# coding: utf-8

# --- Imports
import API
import os
import PO_functions
from PO_portfolio import PO_portfolio
from PO_thermic_constraints import GetVariablesAndConstraints_Thermics
from PO_hydraulic_constraints import GetVariablesAndConstraints_Hydraulics
from PO_storage_constraints import GetVariablesAndConstraints_Storage
from PO_wind_pv_constraints import GetVariablesAndConstraints_wind_pv
from PO_load_constraints import GetVariablesAndConstraints_load
from manual_activation import set_manual_activation


# --- Script
# Main function
def OptimalPlacement(output_marker, p):
    """
    Browse though all portfolios and equipments in output_marker and call the unit commitment function OptimalPlacementCompute
    depending on the bidding mode chosen in parameters:
    _ Portfolio bidding: all equipments in a given portfolio are included in the same optimization problem
    _ Unit-based: an individual optimization problem is applied to each equipment in the marker

    """
    opt_equipments_DT = []
    opt_equipments_DH = []
    opt_equipments_DS = []
    opt_equipments_NDL = []
    opt_equipments_DL = []
    opt_equipments_Wind = []
    opt_equipments_PV = []
    opt_equipments_NDP = []

    # Thermic
    for equipment in output_marker.Thermic.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif equipment.Strategy in p.excluded_thermal_strategies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} with excluded strategy {} is manually activated".format(
                        equipment.Name, equipment.Strategy
                    )
                )
        elif p.is_portfolio_bidding:
            opt_equipments_DT.append(equipment)
        else:
            OptimalPlacement_compute(
                output_marker, [equipment.Portfolio], [equipment], [], [], [], [], [], [], [], equipment, p
            )

    # Hydraulic
    for equipment in output_marker.Hydraulic.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif p.is_portfolio_bidding:
            opt_equipments_DH.append(equipment)
        else:
            OptimalPlacement_compute(
                output_marker, [equipment.Portfolio], [], [equipment], [], [], [], [], [], [], equipment, p
            )

    # Storage
    for equipment in output_marker.Storage.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif p.is_portfolio_bidding:
            opt_equipments_DS.append(equipment)
        else:
            OptimalPlacement_compute(
                output_marker, [equipment.Portfolio], [], [], [equipment], [], [], [], [], [], equipment, p
            )

    # Load
    for equipment in output_marker.Load.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif p.is_portfolio_bidding:
            # Power to gas equipments are dispatchable, the rest is considered non dispatchable
            # (DSR is modeled using thermal units)
            if equipment.LoadType == "PowerToGas":
                opt_equipments_DL.append(equipment)
            else:
                opt_equipments_NDL.append(equipment)
        else:
            if equipment.LoadType == "PowerToGas":
                OptimalPlacement_compute(
                    output_marker, [equipment.Portfolio], [], [], [], [], [equipment], [], [], [], equipment, p
                )
            else:
                OptimalPlacement_compute(
                    output_marker, [equipment.Portfolio], [], [], [], [equipment], [], [], [], [], equipment, p
                )

    # Wind
    for equipment in output_marker.Wind.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif p.is_portfolio_bidding:
            opt_equipments_Wind.append(equipment)
        else:
            OptimalPlacement_compute(
                output_marker, [equipment.Portfolio], [], [], [], [], [], [equipment], [], [], equipment, p
            )

    # PV
    for equipment in output_marker.Photovoltaic.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif p.is_portfolio_bidding:
            opt_equipments_PV.append(equipment)
        else:
            OptimalPlacement_compute(
                output_marker, [equipment.Portfolio], [], [], [], [], [], [], [equipment], [], equipment, p
            )

    # Non dispatchable generation
    for equipment in output_marker.OtherNonDispatchable.GetAllInstances():
        if equipment.Class in p.excluded_technologies:
            set_manual_activation([equipment], p)
            if p.verbose:
                API.IO.Trace.Log(
                    "Equipment {} of excluded type {} is manually activated".format(equipment.Name, equipment.Class)
                )
        elif p.is_portfolio_bidding:
            opt_equipments_NDP.append(equipment)
        else:
            OptimalPlacement_compute(
                output_marker, [equipment.Portfolio], [], [], [], [], [], [], [], [equipment], equipment, p
            )

    if p.is_portfolio_bidding:
        OptimalPlacement_compute(
            output_marker,
            output_marker.Portfolio.AllInstances,
            opt_equipments_DT,
            opt_equipments_DH,
            opt_equipments_DS,
            opt_equipments_NDL,
            opt_equipments_DL,
            opt_equipments_Wind,
            opt_equipments_PV,
            opt_equipments_NDP,
            None,
            p,
        )


# Main unit commitment function
def OptimalPlacement_compute(
    output_marker,
    opt_portfolios,
    equipments_DT,
    equipments_DH,
    equipments_DS,
    equipments_NDL,
    equipments_DL,
    equipments_Wind,
    equipments_PV,
    equipments_NDP,
    equipment,
    p,
):
    """
    Builds and solves the unit commitment optimization problem
    """
    lst_msg_status = []  # This list will contain the status

    for opt_portfolio in opt_portfolios:
        # For excluded market areas, directly fill output marker with results of the previous clearing
        # Not relevant is the PO is used in Forecast mode
        if not p.use_forecast:
            if opt_portfolio.MarketArea.Name in p.excluded_market_areas:
                if p.is_portfolio_bidding:
                    API.IO.Trace.Log(
                        "Portfolio {} is in an excluded market area, and is not optimized".format(opt_portfolio.Name),
                        API.IO.LogTypeWarn,
                    )
                    set_manual_activation(opt_portfolio.GetChildren("Equipment"), p)
                    continue

                else:
                    API.IO.Trace.Log(
                        "Equipment {} is in an excluded market area, and is not optimized".format(equipment.Name),
                        API.IO.LogTypeWarn,
                    )
                    set_manual_activation([equipment], p)
                    continue

        opt_equipments_DT = []
        opt_equipments_DH = []
        opt_equipments_DS = []
        opt_equipments_NDL = []
        opt_equipments_DL = []
        opt_equipments_Wind = []
        opt_equipments_PV = []
        opt_equipments_NDP = []

        # test if there is some equipment in the portfolio, else, no computation is done
        hasGotEquipment = 0

        for local_equipment in equipments_DT:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_DT.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_DH:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_DH.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_DS:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_DS.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_NDL:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_NDL.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_DL:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_DL.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_Wind:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_Wind.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_PV:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_PV.append(local_equipment)
                hasGotEquipment = 1
        for local_equipment in equipments_NDP:
            if local_equipment.Portfolio.Name == opt_portfolio.Name:
                opt_equipments_NDP.append(local_equipment)
                hasGotEquipment = 1

        # if there is no equipment in the portfolio no computation is done
        if hasGotEquipment == 0:
            continue

        if p.is_portfolio_bidding:
            msg = "----- portfolio : {} -----".format(opt_portfolio.Name)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        else:
            msg = "----- equipment : {} -----".format(equipment.Name)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        # Creates the 'PROB' variable to contain the problem data
        # The sense of the optimisation is maximize of benefits.
        if p.is_portfolio_bidding:
            PROB = API.Solver.NewOpProblem(opt_portfolio.Name, API.Solver.OpCategoryBinary, API.Solver.OpSenseMinimize)
        else:
            PROB = API.Solver.NewOpProblem(equipment.Name, API.Solver.OpCategoryBinary, API.Solver.OpSenseMinimize)

        # create portfolio object and fill equipments
        POportfolio = PO_portfolio(opt_portfolio.Name)

        # Get the longest optimisation periode
        max_op_time = sorted(
            [p.op_times, p.thermal_op_times, p.hydraulic_op_times, p.battery_op_times, p.phs_op_times, p.ev_op_times],
            key=lambda x: len(x),
        )[-1]
        POportfolio.InitVariablesAndPreComputations(
            opt_portfolio,
            opt_equipments_DT,
            opt_equipments_DH,
            opt_equipments_DS,
            opt_equipments_Wind,
            opt_equipments_PV,
            opt_equipments_NDP,
            opt_equipments_NDL,
            opt_equipments_DL,
            max_op_time,
            p,
        )

        # get objective function and its constraints
        objFunction = API.Solver.CreateListOpAffineExpression()
        constraintList = API.Solver.CreateListOpConstraint()
        globalConstraintList = API.Solver.CreateListOpConstraint()

        for time_enum, time in enumerate(max_op_time):
            if time in p.target_times:
                # debug
                if p.debug:
                    API.IO.Trace.Log(
                        "Small imbalance price up at time {} : {}".format(time, str(POportfolio.imbal_price_up[time])),
                        API.IO.LogTypeInfo,
                    )

                    API.IO.Trace.Log(
                        "Large imbalance price up at time {} : {}".format(
                            time, str(POportfolio.large_imbal_price_up[time])
                        ),
                        API.IO.LogTypeInfo,
                    )

                    API.IO.Trace.Log(
                        "Small imbalance price down at time {} : {}".format(
                            time, str(POportfolio.imbal_price_down[time])
                        ),
                        API.IO.LogTypeInfo,
                    )

                    API.IO.Trace.Log(
                        "Large imbalance price down at time {} : {}".format(
                            time, str(POportfolio.large_imbal_price_down[time])
                        ),
                        API.IO.LogTypeInfo,
                    )

                # objective function, portfolio parameters
                objFunction.Add(
                    POportfolio.imbal_price_up[time] * POportfolio.Small_imbal_up[time] * p.time_step / 60.0
                )
                objFunction.Add(
                    POportfolio.large_imbal_price_up[time] * POportfolio.Large_imbal_up[time] * p.time_step / 60.0
                )
                objFunction.Add(
                    -POportfolio.imbal_price_down[time] * POportfolio.Small_imbal_down[time] * p.time_step / 60.0
                )
                objFunction.Add(
                    -POportfolio.large_imbal_price_down[time] * POportfolio.Large_imbal_down[time] * p.time_step / 60.0
                )

            sum_power_level = API.Solver.CreateListOpVariable()

            reserveProcureUpti = API.Solver.CreateListOpVariable()
            reserveProcureDownti = API.Solver.CreateListOpVariable()
            automatedReserveProcureUpti = API.Solver.CreateListOpVariable()
            automatedReserveProcureDownti = API.Solver.CreateListOpVariable()

            if time in p.op_times:
                # Add constraints and elements in objective function related to wind and pv units
                GetVariablesAndConstraints_wind_pv(
                    time,
                    POportfolio.wind,
                    objFunction,
                    constraintList,
                    sum_power_level,
                    reserveProcureUpti,
                    reserveProcureDownti,
                    automatedReserveProcureUpti,
                    automatedReserveProcureDownti,
                    POportfolio.priceForecast,
                    p,
                )
                GetVariablesAndConstraints_wind_pv(
                    time,
                    POportfolio.pv,
                    objFunction,
                    constraintList,
                    sum_power_level,
                    reserveProcureUpti,
                    reserveProcureDownti,
                    automatedReserveProcureUpti,
                    automatedReserveProcureDownti,
                    POportfolio.priceForecast,
                    p,
                )

            if time in p.thermal_op_times:
                # Add constraints and elements in objective function related to thermal units
                GetVariablesAndConstraints_Thermics(
                    time,
                    POportfolio.thermics,
                    objFunction,
                    constraintList,
                    sum_power_level,
                    reserveProcureUpti,
                    reserveProcureDownti,
                    automatedReserveProcureUpti,
                    automatedReserveProcureDownti,
                    POportfolio.priceForecast,
                    p,
                )

            if time in p.hydraulic_op_times:
                # Add constraints and elements in objective function related to hydraulic units
                GetVariablesAndConstraints_Hydraulics(
                    time,
                    POportfolio.hydraulics,
                    objFunction,
                    constraintList,
                    sum_power_level,
                    reserveProcureUpti,
                    reserveProcureDownti,
                    automatedReserveProcureUpti,
                    automatedReserveProcureDownti,
                    POportfolio.priceForecast,
                    p,
                )

            if time in p.battery_op_times or time in p.phs_op_times or time in p.ev_op_times:
                # Add constraints and elements in objective function related to storage units
                GetVariablesAndConstraints_Storage(
                    time,
                    POportfolio.storage,
                    objFunction,
                    constraintList,
                    sum_power_level,
                    reserveProcureUpti,
                    reserveProcureDownti,
                    automatedReserveProcureUpti,
                    automatedReserveProcureDownti,
                    POportfolio.priceForecast,
                    p,
                )

            if time in p.op_times:
                # Add constraints and elements in objective function related to dispatchable load units
                GetVariablesAndConstraints_load(
                    time,
                    POportfolio.load,
                    objFunction,
                    constraintList,
                    sum_power_level,
                    reserveProcureUpti,
                    reserveProcureDownti,
                    automatedReserveProcureUpti,
                    automatedReserveProcureDownti,
                    POportfolio.priceForecast,
                    p,
                )

            # On each period of duration deltat and starting at t_i in T \ {t_n}
            # the value of the positive or negative deviation is equal to the energy still to be supplied
            # by the perimeter following the calculation of the program of the non- Dispatchable equipment
            # and prior to the calculation of the dispatchable equipment program less
            # what the dispatchable equipment provide:
            # contractedDifference

            if time in p.target_times:
                # Add reserves constraints only if the portfolio has got generation equipments
                if (
                    len(opt_equipments_DT)
                    + len(opt_equipments_DH)
                    + len(opt_equipments_DS)
                    + len(opt_equipments_Wind)
                    + len(opt_equipments_PV)
                    > 0
                ):
                    constraintList.Add(
                        POportfolio.contractedDifferenceUp[time]
                        >= POportfolio.reserve_Up[time] - API.Solver.OpSum(reserveProcureUpti)
                    )
                    objFunction.Add(
                        p.manual_unprocured_reserves_penalty
                        * (p.time_step / 60.0)
                        * POportfolio.contractedDifferenceUp[time]
                    )
                    constraintList.Add(
                        POportfolio.contractedDifferenceDown[time]
                        >= POportfolio.reserve_Down[time] - API.Solver.OpSum(reserveProcureDownti)
                    )
                    objFunction.Add(
                        p.manual_unprocured_reserves_penalty
                        * (p.time_step / 60.0)
                        * POportfolio.contractedDifferenceDown[time]
                    )

                    # automatedContractedDifference
                    constraintList.Add(
                        POportfolio.automatedContractedDifferenceUp[time]
                        >= (POportfolio.automated_Reserve_Up[time] - API.Solver.OpSum(automatedReserveProcureUpti))
                    )
                    objFunction.Add(
                        p.automated_unprocured_reserves_penalty
                        * (p.time_step / 60.0)
                        * POportfolio.automatedContractedDifferenceUp[time]
                    )
                    constraintList.Add(
                        POportfolio.automatedContractedDifferenceDown[time]
                        >= (POportfolio.automated_Reserve_Down[time] - API.Solver.OpSum(automatedReserveProcureDownti))
                    )
                    objFunction.Add(
                        p.automated_unprocured_reserves_penalty
                        * (p.time_step / 60.0)
                        * POportfolio.automatedContractedDifferenceDown[time]
                    )

                globalConstraintList.Add(
                    POportfolio.Small_imbal_up[time]
                    + POportfolio.Large_imbal_up[time]
                    - POportfolio.Small_imbal_down[time]
                    - POportfolio.Large_imbal_down[time]
                    == POportfolio.residualEnergy[time] - API.Solver.OpSum(sum_power_level)
                )

                # -- Upward and downward imbalances in the portfolio are below the maximum allowed
                globalConstraintList.Add(
                    POportfolio.Small_imbal_up[time] + POportfolio.Large_imbal_up[time]
                    <= POportfolio.max_overall_imbal[time]
                )
                globalConstraintList.Add(
                    POportfolio.Small_imbal_down[time] + POportfolio.Large_imbal_down[time]
                    <= POportfolio.max_overall_imbal[time]
                )

        msg = "Adding objective function and variables..."
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        # Add Objective function to prob
        PROB.NoOverlap = False
        PROB.SetObjective(API.Solver.OpSum(objFunction))

        # Add each constraint:
        PROB.AddConstraints(globalConstraintList)
        PROB.AddConstraints(constraintList)

        # Fill all parameters of the solver
        if p.solver.upper() == "XPRESS":
            optim_solver = PROB.NewOpSolver("xpress")

            if p.presolve:
                xpress_presolve = "1"
            else:
                xpress_presolve = "0"

            # Some solver parameters as examples (not required)
            """CUTFACTOR=5
            CUTFREQ=2
            GOMCUTS=2
            PRESOLVE=0
            SBESTIMATE=3
            SYMMETRY=1"""

            optim_solver.SetSolverSpecificParameters(
                "MAXTIME {} MIPRELSTOP {} PRESOLVE {}".format(str(p.time_out), str(p.duality_gap), xpress_presolve)
            )

        else:
            PROB.Presolve = p.presolve
            PROB.MpsOutput = False
            PROB.Algorithm = API.Solver.OpAlgorithmSimplex
            PROB.DualityGap = p.duality_gap
            PROB.Timeout = p.time_out

        # Print LP
        if p.debug:
            if p.is_portfolio_bidding:
                lp_file_name = os.path.join(p.output_folder, "Portfolio_{}.lp".format(opt_portfolio.Name))
            else:
                lp_file_name = os.path.join(p.output_folder, "Equipment_{}.lp".format(equipment.Name))

            if p.solver.upper() == "XPRESS":
                PROB.WriteLP(lp_file_name, True)

            else:
                PROB.WriteLP(lp_file_name)

                print(open(API.Workspace + "\\" + lp_file_name, "r").read())

        if p.solver in ["GLPK", "PNE"]:
            PROB.Solve(p.solver)
        elif p.solver.upper() == "XPRESS":
            PROB.SolveORTools(optim_solver)
        else:
            PROB.SolveORTools(p.solver)

        # export solution results
        API.Solver.ExportSolution(PROB, "solution_%s.out" % PROB.Name)

        # The status of the solution is printed to the screen
        msg = "Resolution ends with Status = {}".format(PROB.Status)
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        # the objective function result is printed to the screen
        msg = "The total cost is: {} E".format(API.Solver.Value(PROB.Objective))
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        lst_msg_status.append(
            "%s end with status %s" % (opt_portfolio.Name, PROB.Status)
        )  # Add the solver status to the list

        # ------ Outputs ------

        # If the optimization was not successful, revert to the manual activation mode
        if str(PROB.Status) != "Optimal":
            if p.is_portfolio_bidding:
                set_manual_activation(opt_portfolio.GetChildren("Equipment"), p)
            else:
                set_manual_activation([equipment], p)
            continue

        # --- Portfolio exports, only in Portfolio mode
        # In portfolio mode, the imbalance of each portfolio is stored in the associated matrix
        if p.debug and p.is_portfolio_bidding:
            for time in p.target_times:
                API.IO.Trace.Log(
                    "Large upward imbalance of PO {} at time {}: {}".format(
                        POportfolio.name, time, POportfolio.Large_imbal_up[time].VarValue
                    ),
                    API.IO.LogTypeInfo,
                )
                API.IO.Trace.Log(
                    "Large downward imbalance of PO {} at time {}: {}".format(
                        POportfolio.name, time, POportfolio.Large_imbal_down[time].VarValue
                    ),
                    API.IO.LogTypeInfo,
                )
                API.IO.Trace.Log(
                    "Small upward imbalance of PO {} at time {}: {}".format(
                        POportfolio.name, time, POportfolio.Small_imbal_up[time].VarValue
                    ),
                    API.IO.LogTypeInfo,
                )
                API.IO.Trace.Log(
                    "Small downward imbalance of PO {} at time {}: {}".format(
                        POportfolio.name, time, POportfolio.Small_imbal_down[time].VarValue
                    ),
                    API.IO.LogTypeInfo,
                )

        if p.is_portfolio_bidding:
            imbalance_ts = API.TimeSeries.NewTimeSeries("Imbalance", API.TimeSeries.Constant, "MW", p.target_times, 0)

            for time in p.target_times:
                imbalance_ts.SetValue(
                    time,
                    (
                        POportfolio.Large_imbal_down[time].VarValue
                        + POportfolio.Small_imbal_down[time].VarValue
                        - POportfolio.Large_imbal_up[time].VarValue
                        - POportfolio.Small_imbal_up[time].VarValue
                    ),
                )

            opt_portfolio.Imbalance.AddTimeSeries(p.execution_date, imbalance_ts)

        # Export the the total power of the portfolio (by convention, positive for injection and negative for consumption)
        if p.is_portfolio_bidding:
            power_ts = API.TimeSeries.NewTimeSeries("PO_power", API.TimeSeries.Constant, "MW", p.target_times, 0)

            equipment_list = opt_portfolio.GetChildren("Equipment")

            for time in p.target_times:
                for marker_equipment in equipment_list:
                    power_ts.SetValue(
                        time,
                        power_ts.GetValue(time)
                        + marker_equipment.Power.GetForecast(p.execution_date, time, time).GetValue(time),
                    )

            if p.execution_date in opt_portfolio.Power.Index:
                opt_portfolio.Power.DeleteTimeSeries(p.execution_date)
            opt_portfolio.Power.AddTimeSeries(p.execution_date, power_ts)

        # Thermic Equipments
        for equipment_name, optim_equipment in POportfolio.thermics.items():
            marker_equipment = output_marker.Thermic.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, optim_equipment, "Thermic", p)

        # Hydraulic Equipments
        for equipment_name, optim_equipment in POportfolio.hydraulics.items():
            marker_equipment = output_marker.Hydraulic.GetInstanceByName(optim_equipment.name)
            output_marker_update(marker_equipment, optim_equipment, "Hydraulic", p)

        # Storage Equipments
        for equipment_name, optim_equipment in POportfolio.storage.items():
            marker_equipment = output_marker.Storage.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, optim_equipment, "Storage", p)

        # Wind
        for equipment_name, optim_equipment in POportfolio.wind.items():
            marker_equipment = output_marker.Wind.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, optim_equipment, "Wind", p)

        # Photovoltaic
        for equipment_name, optim_equipment in POportfolio.pv.items():
            marker_equipment = output_marker.Photovoltaic.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, optim_equipment, "Photovoltaic", p)

        # Dispatchable Load
        for equipment_name, optim_equipment in POportfolio.load.items():
            marker_equipment = output_marker.Load.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, optim_equipment, "Load", p)

        # Non dispatchable Load
        for equipment_name, dispatch_values in POportfolio.Optimal_dispatch_NDL.items():
            marker_equipment = output_marker.Load.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, dispatch_values, "Optimal_Dispatch_NDL", p)

        # Non dispatchable Equipments
        for equipment_name, dispatch_values in POportfolio.Optimal_dispatch_NDP.items():
            marker_equipment = output_marker.OtherNonDispatchable.GetInstanceByName(equipment_name)
            output_marker_update(marker_equipment, dispatch_values, "Optimal_Dispatch_NDP", p)

    # Return all status msg in the log
    for msg_i in lst_msg_status:
        API.IO.Trace.Log(msg_i, API.IO.LogTypeInfo)


# Output function
def output_marker_update(marker_equipment, optim_equipment, equipment_type, p):
    """
    Writes results of the Portfolio Optimization in the output marker.
    The following elements are updated, depending on the equipment type:
    _ Power for all equipments, and for all portfolios (in portfolio bidding mode)
    _ StoredEnergy for Hydraulic and Storage equipments
    _ Imbalance of all portfolios (in portfolio bidding mode)

    Note: as optimization results may include rounding artefacts (notably infinitesimal values or decimals),
    a rounding process is applied to all optimization outputs. It is managed by the function power_output_rounding
    """

    # --- Extract Power and StoredEnergy timeseries
    # For most types of equipments, it corresponds to the output of the optimization problem
    if equipment_type not in ["Optimal_Dispatch_NDP", "Optimal_Dispatch_NDL"]:
        # Initialization
        new_prog = API.TimeSeries.NewTimeSeries(
            "Final Program",
            API.TimeSeries.Constant,
            "MW",
            p.target_times,
            [optim_equipment.MaximumPower[time] for time in p.target_times],
        )

        if equipment_type in ["Hydraulic", "Storage"]:
            new_stored_energy = API.TimeSeries.NewTimeSeries(
                "StoredEnergy",
                API.TimeSeries.Constant,
                "MWh",
                p.target_times,
                [optim_equipment.MaximumEnergy[time] for time in p.target_times],
            )

        # new_prog is the Power output for Optimization Process, with specificities for Hydraulic and Storage equipments
        # In the optim problem, it is defined on more TimeSteps than necessary (Initial Condions +
        # Delivery Timeframe + Additional Hours). We only extract the time steps corresponding to TargetTimes

        # Filling Timeseries
        if equipment_type == "Hydraulic":
            for time in p.target_times:
                # Power
                activated_power = 0
                for k in range(0, len(marker_equipment.FragmentVolumes)):
                    activated_power += optim_equipment.PowerLevelFragment[k][time].VarValue

                if activated_power <= p.allowed_round_off_error:
                    activated_power = 0

                new_prog.SetValue(time, activated_power)

                # Energy
                new_stored_energy.SetValue(time, optim_equipment.StoredEnergy[time].VarValue)

        elif equipment_type == "Storage":
            for time in p.target_times:
                # Power
                activated_power = (
                    optim_equipment.PowerLevelBuy[time].VarValue + optim_equipment.PowerLevelSell[time].VarValue
                )

                if abs(activated_power) <= p.allowed_round_off_error:
                    activated_power = 0

                new_prog.SetValue(time, activated_power)

                # Energy
                new_stored_energy.SetValue(time, optim_equipment.StoredEnergy[time].VarValue)

        else:
            for time in p.target_times:
                new_prog.SetValue(time, optim_equipment.PowerLevel[time].VarValue)

    # For non dispatchable equipments, the power output is set to the minimum between the market commitments
    # and the technical capacity of the equipment.
    else:
        new_prog = API.TimeSeries.NewTimeSeries(
            "Final Program",
            API.TimeSeries.Constant,
            "MW",
            p.target_times,
            [optim_equipment[time] for time in p.target_times],
        )

    # --- Rounding process
    if p.with_rounding:
        new_prog = power_output_rounding(marker_equipment, new_prog, p)
        if equipment_type in ["Hydraulic", "Storage"]:
            new_stored_energy = stored_energy_rounding(marker_equipment, new_stored_energy, p)

    # --- State sequence for Thermal equipments
    if equipment_type == "Thermic":
        state_sequence = API.TimeSeries.NewTimeSeries(
            "StateSequence", API.TimeSeries.Constant, "", p.thermal_op_times, 0
        )

        for time in state_sequence.Index:
            if optim_equipment.ON_UP[time].VarValue == 1:
                state_sequence.SetValue(time, 1)

            if optim_equipment.ON_DOWN[time].VarValue == 1:
                state_sequence.SetValue(time, 2)

            if optim_equipment.OFF[time].VarValue == 1:
                state_sequence.SetValue(time, 3)

            if optim_equipment.T_start >= 1:
                if optim_equipment.START[time].VarValue == 1:
                    state_sequence.SetValue(time, 4)

            if optim_equipment.T_stop >= 1:
                if optim_equipment.STOP[time].VarValue == 1:
                    state_sequence.SetValue(time, 5)

            if optim_equipment.T_stable >= 1:
                if optim_equipment.ON_FLAT[time].VarValue == 1:
                    state_sequence.SetValue(time, 6)

    # --- Export in the output marker
    if p.use_forecast:
        if p.execution_date in marker_equipment.IDPOForOrders.Index:
            marker_equipment.IDPOForOrders.DeleteTimeSeries(p.execution_date)
        marker_equipment.IDPOForOrders.AddTimeSeries(p.execution_date, new_prog)

        if equipment_type == "Thermic":
            marker_equipment.StateSequence.AddTimeSeries(
                "{}_PO_Forecast".format(PO_functions.get_date_to_clean_string(p.execution_date)), state_sequence
            )
    else:
        if p.execution_date in marker_equipment.Power.Index:
            marker_equipment.Power.DeleteTimeSeries(p.execution_date)
        marker_equipment.Power.AddTimeSeries(p.execution_date, new_prog)

        if equipment_type == "Thermic":
            marker_equipment.StateSequence.AddTimeSeries(
                "{}_PO".format(PO_functions.get_date_to_clean_string(p.execution_date)), state_sequence
            )

        if equipment_type in ["Hydraulic", "Storage"]:
            if p.execution_date in marker_equipment.StoredEnergy.Index:
                marker_equipment.StoredEnergy.DeleteTimeSeries(p.execution_date)
            marker_equipment.StoredEnergy.AddTimeSeries(p.execution_date, new_stored_energy)


# Rounding functions
def power_output_rounding(marker_equipment, Power_TimeSeries, p):
    """
    Rounds power timeseries at 2 decimals, while performing the following checks:
    _ The rounded power should not be out of bounds (above MaximumPower / below 0 or MinimumPower)
    _ "Flat" power states should be kept by the rounding process
    _ In case of a thermal unit with active MinimumStablePowerDuration constraint,
      ramps should be kept at a constant grade by the rounding process
    """

    rounding_precision = 2
    accepted_error = 0.01
    SD_minus_one = p.start_date.AddMinutes(-p.time_step)
    SD_minus_two = p.start_date.AddMinutes(-2 * p.time_step)

    if marker_equipment.Class not in ["Wind", "Photovoltaic", "Load", "OtherNonDispatchable"]:
        max_power = marker_equipment.MaximumPower
        min_power = marker_equipment.MinimumPower

    if marker_equipment.Class in ["Wind", "Photovoltaic", "OtherNonDispatchable"]:
        max_power = marker_equipment.MaximumPowerForecast.GetForecast(
            p.execution_date, Power_TimeSeries.FirstDate, Power_TimeSeries.LastDate
        )
        min_power = API.TimeSeries.NewTimeSeries("MinPower", API.TimeSeries.Constant, "MW", Power_TimeSeries.Index, 0)

    if marker_equipment.Class == "Load":
        min_power = marker_equipment.MaximumPowerForecast.GetForecast(
            p.execution_date, Power_TimeSeries.FirstDate, Power_TimeSeries.LastDate
        )

        max_power = API.TimeSeries.NewTimeSeries("MaxPower", API.TimeSeries.Constant, "MW", Power_TimeSeries.Index, 0)

    for time_t in Power_TimeSeries.Index:
        # STEP 1: ROUNDING VALUES:

        Power_TimeSeries.SetValue(time_t, round(Power_TimeSeries.GetValue(time_t), rounding_precision))

        # STEP 2: MAX, MIN AND NULL POWER CORRECTIONS:

        power_to_floor = Power_TimeSeries.GetValue(time_t)
        power_floored = Power_TimeSeries.GetValue(time_t)

        maxPower_at_t = max_power.GetValue(time_t)
        minPower_at_t = min_power.GetValue(time_t)

        # Null case:
        if abs(power_to_floor) <= accepted_error:
            power_floored = 0

        # MinPower case:
        if abs(power_to_floor - minPower_at_t) <= accepted_error:
            power_floored = minPower_at_t

        # MaxPower case:
        if abs(power_to_floor - maxPower_at_t) <= accepted_error:
            power_floored = maxPower_at_t

        if power_to_floor != power_floored:
            if p.debug:
                API.IO.Trace.Log(
                    "Rounding correction for equipment {} at time {}: Out of bound".format(
                        marker_equipment.Name, str(time_t)
                    ),
                    API.IO.LogTypeWarn,
                )
            Power_TimeSeries.SetValue(time_t, power_floored)

    # STEP 3: FLAT POWER CORRECTION:

    for time_t in Power_TimeSeries.Index:
        if time_t == Power_TimeSeries.FirstDate:
            if Power_TimeSeries.GetValue(SD_minus_one):
                # TS Transition:
                power_sd_minus_1 = marker_equipment.Power.GetForecast(
                    p.execution_date, SD_minus_one, p.start_date
                ).GetValue(SD_minus_one)
            else:
                # First date of simulation, no modification required
                continue

        else:
            power_sd_minus_1 = Power_TimeSeries.GetValue(SD_minus_one)

            if abs(Power_TimeSeries.GetValue(time_t) - power_sd_minus_1) <= accepted_error:
                if p.debug:
                    API.IO.Trace.Log(
                        "Rounding correction for equipment {} at time {}: Flat power".format(
                            marker_equipment.Name, str(time_t)
                        ),
                        API.IO.LogTypeWarn,
                    )
                Power_TimeSeries.SetValue(time_t, power_sd_minus_1)

    # STEP 4: RAMPING POWER CORRECTION:

    # Dict built as: delta_P[date] = P[date+1] - P[date]
    delta_P = {}

    if marker_equipment.Class == "Thermic":
        if marker_equipment.MinimumStablePowerDuration > 1:
            # First we add the previous tf last step of simulation to calibrate the start_date in case ramping started on SD-1:
            # copy of Power_TimeSeries:
            extended_Power_TimeSeries = API.TimeSeries.NewTimeSeries(Power_TimeSeries)

            power_sd_minus_1 = marker_equipment.Power.GetForecast(
                p.execution_date, SD_minus_one, p.start_date
            ).GetValue(SD_minus_one)

            # Add of the last power value:
            extended_Power_TimeSeries.SetValue(SD_minus_one, power_sd_minus_1)

            # Building delta_P:
            for time_t in extended_Power_TimeSeries.Index:
                # We ignore LastDate as nextPower doesn't exist for this date:
                if time_t == extended_Power_TimeSeries.LastDate:
                    continue

                # Ramping:
                nextPower = extended_Power_TimeSeries.GetValue(time_t.AddMinutes(p.time_step))

                if extended_Power_TimeSeries.GetValue(time_t) != nextPower:
                    delta_P[time_t] = nextPower - extended_Power_TimeSeries.GetValue(time_t)

                # Case P[t] == P[t_next]:
                else:
                    delta_P[time_t] = 0

            # List containing already corrected indexes
            corrected_ts = []

            previous_tf_ramp_prolongation = False

            # We have to verify if the ramping started before SD-1 and continues in the current tf,
            # if it's the case the delta P bewtween SD-2 and SD-1 has to be applied to the whole ramp.
            # If the ramping started on SD-1 the corrections will be normally applied

            if (SD_minus_one in delta_P.keys()) and (p.start_date in delta_P.keys()):
                power_sd_minus_2 = marker_equipment.Power.GetForecast(
                    p.execution_date, SD_minus_two, SD_minus_one
                ).GetValue(SD_minus_two)

                previous_fixed_delta_P = power_sd_minus_1 - power_sd_minus_2

                if previous_fixed_delta_P != 0:
                    # previous_fixed_delta_P has to applied to the whole ramp we activate this with a boolean value:
                    previous_tf_ramp_prolongation = True

            for time_t in sorted(delta_P.keys()):
                # Skip already corrected values
                if time_t in corrected_ts:
                    continue

                # Skip flat states
                if delta_P[time_t] == 0:
                    continue

                # Build current ramp:
                current_ramp = [time_t]

                for time_step_iterator in range(1, len(extended_Power_TimeSeries.Index)):
                    potential_next_ramping_index = time_t.AddMinutes(p.time_step * time_step_iterator)

                    # Checks if potential_next_ramping_index is in the timeframe
                    if potential_next_ramping_index not in delta_P.keys():
                        break

                    # Checks if potential_next_ramping_index is still ramping
                    if delta_P[potential_next_ramping_index] == 0:
                        break

                    # Finally, check if potential_next_ramping_index corresponds to the MinimumPower of the unit
                    # If it is the case, then the ramp should be considered as finished
                    # (as the gradient may change for startup / shutdown periods)
                    if (
                        abs(
                            extended_Power_TimeSeries.GetValue(potential_next_ramping_index)
                            - marker_equipment.MinimumPower.GetValue(potential_next_ramping_index)
                        )
                        < accepted_error
                    ):
                        break

                    current_ramp.append(potential_next_ramping_index)

                # If ramping time is one we skip:
                if len(current_ramp) <= 1:
                    continue

                # delta_P_corrected_value is the previous time frame delta if in previous_tf_ramp_prolongation
                elif (time_t == SD_minus_one) and (previous_tf_ramp_prolongation) and len(current_ramp) >= 1:
                    # we force the delta_p from previous tf:
                    delta_P_corrected_value = previous_fixed_delta_P
                    if p.debug:
                        API.IO.Trace.Log(
                            "Rounding correction for equipment {} at time {}: Ramping".format(
                                marker_equipment.Name, str(time_t)
                            ),
                            API.IO.LogTypeWarn,
                        )

                else:
                    first_ramp_value = extended_Power_TimeSeries.GetValue(current_ramp[0])

                    last_ramp_value = extended_Power_TimeSeries.GetValue(current_ramp[-1].AddMinutes(p.time_step))

                    delta_P_corrected_value = (last_ramp_value - first_ramp_value) / len(current_ramp)

                for ramping_index_minus_one in current_ramp[:-1]:
                    ramping_index = ramping_index_minus_one.AddMinutes(p.time_step)

                    new_q = round(
                        extended_Power_TimeSeries.GetValue(ramping_index)
                        - delta_P[ramping_index_minus_one]
                        + delta_P_corrected_value,
                        2,
                    )
                    if p.debug:
                        API.IO.Trace.Log(
                            "Rounding correction for equipment {} at time {}: Ramping".format(
                                marker_equipment.Name, str(ramping_index)
                            ),
                            API.IO.LogTypeWarn,
                        )
                    Power_TimeSeries.SetValue(ramping_index, new_q)

                    corrected_ts.append(ramping_index)

    return Power_TimeSeries


def stored_energy_rounding(marker_equipment, energy_timeseries, p):
    """
    Rounds StoredEnergy timeseries at 2 decimals, while performing the following check:
    _ The rounded energy should not be out of bounds (above MaximumEnergy / below MinimumEnergy)
    """

    rounding_precision = 2
    accepted_error = 0.01

    if marker_equipment.Class == "Hydraulic":
        max_energy = marker_equipment.MaximumEnergy.Extract("LocalMaxEnergy", energy_timeseries.Index)
        min_energy = marker_equipment.MinimumEnergy.Extract("LocalMinEnergy", energy_timeseries.Index)

    if marker_equipment.Class == "Storage":
        max_energy = marker_equipment.MaximumEnergy.Extract("LocalMaxEnergy", energy_timeseries.Index)

        min_energy = API.TimeSeries.NewTimeSeries(max_energy)
        min_soc = marker_equipment.MinimumStateOfCharge.Extract("LocalMinSOC", energy_timeseries.Index)
        for time in min_energy.Index:
            min_energy.SetValue(time, max_energy.GetValue(time) * min_soc.GetValue(time))

    for time_t in energy_timeseries.Index:
        # STEP 1: ROUNDING VALUES:

        energy_timeseries.SetValue(time_t, round(energy_timeseries.GetValue(time_t), rounding_precision))

        # STEP 2: MAX, MIN AND NULL POWER CORRECTIONS:

        energy_to_floor = energy_timeseries.GetValue(time_t)
        energy_floored = energy_timeseries.GetValue(time_t)

        maxEnergy_at_t = max_energy.GetValue(time_t)
        minEnergy_at_t = min_energy.GetValue(time_t)

        # MinEnergy case:
        if abs(energy_to_floor - minEnergy_at_t) <= accepted_error:
            energy_floored = minEnergy_at_t

        # MaxEnergy case:
        if abs(energy_to_floor - maxEnergy_at_t) <= accepted_error:
            energy_floored = maxEnergy_at_t

        if energy_to_floor != energy_floored:
            if p.debug:
                API.IO.Trace.Log(
                    "Rounding correction for equipment {} at time {}: Out of bound energy".format(
                        marker_equipment.Name, str(time_t)
                    ),
                    API.IO.LogTypeWarn,
                )
            energy_timeseries.SetValue(time_t, energy_floored)

    return energy_timeseries
