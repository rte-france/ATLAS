Version 1.1.0
# Introduction
## Definition
 **Area** : In portfolio bidding, the area includes all the equipment of a portfolio. In unit bidding, the area only includes equipment. Other portfolio dispatches can exist.
The area will be an option for the task
**Forecast Program** : it is the declaration of the producer to the network operator of the forecast produce quantity of all their equipment connect to the network. In OPTIMATE, this concept includes all the equipment: generation and load.
## Goal
The goal of this task is to define for each area an optimal forecast produce quantity program. This optimization is done at a specific time for a target time range. In other words, the area define what its produce and/or consume.

---
# Input
To define the optimal placement of its equipment, an area needs to deal with few global parameters:
* *ExecutionDate* , calculation hours of the optimal dispatch by the portfolio
* *StartDate*, task end date parameters.
* *EndDate*, Task end date parameter
* *DeltaTime*, the duration
* *SmallImabalanceLimit*, the quantity (in %) of imbalances qualified as small for the portfolio, relative to the maximum energy that the portfolio can produce
* *SmallImbalancePrice*, the penalty percentage of small imbalances compared to the maximal energy the portfolio can produce.
* *LargeImbalancePrice* , the penalty percentage of large imbalances compared to the maximal energy the portfolio can produce.
* *MaximumImbalance*, The maximum imbalance allows for the program
* *Solver*, The solver types use by the optimization program.
* *AdditionalHours* ,optimization period in hours for all equipment
* *ThermalAdditionalHours* ,optimization period in hours for thermic equipment
* *StorageAdditionalHours* ,optimization period in hours for storage equipment
* *HydraulicAdditionalHours* ,optimization period in hours of hydraulic equipment
* *PumpedHydraulicNumberOfFragments*, Number of power fragments for a pumped hydraulic equipment, at each time step, power supply is divided into fragments, last fragments are more expensive than first ones
* *BatteryNumberOfFragments*, amount of power fragments for a battery equipment at each time step, power supply is divided into fragments, last fragments are more expensive than first ones.
* *ElectricVehicleNumberOfFragments*, Number of power fragments for an electrical vehicle at each time step, power supply is divided into fragments, last fragments are more expensive than first ones
* *BatterySmoothingFactor*, this factor will contribute in smoothing the power offer/demand curve for battery equipment. Value between 0 and 1.
* *ElectricVehicleSmoothingFactor*, this factor will contribute in smoothing the power offer/demand curve for an electric vehicle. Value between 0 and 1.
* *PumpedHydraulicSmoothingFactor*, this factor will contribute in smoothing the power offer/demand curve. Value between 0 and 1.
* *Epsilon*, A slack parameter to avoid infeasibility due to numerical approximations.
* *IsPortfolioBidding*, A boolean indicating if the optimisation should be done for portfolios or with a unit based method.


---
# Functional processes
For each area, we follow these steps:
-	Determine a fatal production/load programs
-	Determine residual energy quantity to beproduced in the area
-	Determine the optimal forecast generation plan
---
# Objective function
The objective function is composed of two parts:
- During the target period, the function minimize cost, find a balance between production cost and imbalance cost.
- During additional time period, the portfolio doesn’t take engagement, the function try to maximize benefit.
We define $T_{OP}$ the optimization period, and $T_{AP_i}$ the additional period, $T_i$ the union between $T_{OP}$ and $T_{AP_i}$. The objective function can be express:
$$
ObjFunction=ImbalanceCostFunction\\
    	+ OperatingCostFunction\\
        - PotentialProfitFunction\\
        + UnprovideReserveCost
$$
With:
$$
ImbalanceCostFunction = \sum_{t_i\in T_{OP}} (ImbalPriceUp_{t_i} * SmallImbalUp_{t_i} \\
    + LargeImbalPriceUp_{t_i} * LargeImbalUp_{t_i} \\
    - ImbalPriceDown_{t_i } * SmallImbalDown_{t_i} \\
    -LargeImbalPriceDown_{t_i} * LargeImbalDown_{t_i })*\frac{\Delta T}{60.0}
$$
$$
OperatingCostFunction=\sum_{t_i\in T_{OP} } ( \sum_ {j\in  DT} (PropCost_j * PowerLevel_{j,t_i} * \frac{\Delta T}{60.0} \\
    + StartUpCost_{j,t_i} * IsStartUp_{j,t_i })\\
    + \sum_{j\in DH} \sum _{f } WaterValue_{t_i,j,f} * ProduceQuantyPower_{t_i,j,f} * \frac{\Delta T}{60.0}\\
    + \sum_{j\in DS} PropCost * (Pa_{j,t}-Pv_{j,t}) * \frac{\Delta T}{60.0})\\
$$
$$
PotentialProfitFunction=\sum_{t_i\in T_{AP}} [\sum_{j \in DT} PriceForecast_{p,t}*PowerLevel_{j,t_i} * \frac{\Delta T}{60.0} \\
   + \sum_{j\in DS} \sum_{n=0}^{ PowerFragments -1}[Pv_{n,t_i}+Pa_{n,t_i}] * ( PriceForecast_{t_i} + n * \epsilon _{t_i})\\
    + \sum _{j\in DH} \sum _{f=0} Vol_{t_i,j,f}*(PriceForecast_{t_i,j,f} - WaterValue_{t_i,j,f} )]
$$
$$
UnprovideReserveCost=+ \sum _{t_i\in T_{op}}((manualUnprocuredReservesPenalty *\frac{\Delta T}{60.0}\\
    *(contractedDifferenceUp_{ti}  - contractedDifferenceDown_{ti} )\\
    + automatedUnprocuredReservesPenalty  * \frac{\Delta T}{60.0} \\
   * (automatedContractedDifferenceUp_{ti}\\
   - automatedContractedDifferenceDown_{ti})))
$$
---
# Constraints
## Area constraints

For each time step $\Delta t$, the global imbalance must be equal to the difference between the energy sold or bought on the market and the energy produced by all Equipments (Dispatchable or not). A portfolio needs to respect the following constraint:

$$
SmallImbalUp_{t_i} + LargeImbalUp_{t_i} - SmallImbalDown_{t_i} - LargeImbalDown_{t_i} = residualEnergy_{t_i} - \sum_{j \in D} PowerLevel_{j,t_i} * \Delta t
$$

A portfolio needs to provide different reserve quantities. Those reserves are defined during previous procurement markets:

$$\sum_{j \in D} AFRRUp_{j,t_i} + \sum_{j \in NDP} AFRRUp_{j,t_i} +\sum_{ j \in NDC} AFRRUp_{j,t_i}= AFRRUpTot_{j,t_i}$$
$$\sum_ {j \in D} AFRRDown_{j,t_i} + \sum_{ j \in NDP} AFRRDown_{j,t_i} +\sum_{j \in NDC}AFRRDown_{j,t_i}=AFRRDownTot_{t_i}$$
$$\sum_{j\in D}MFRRUp_{j,t_i}+\sum_{j\in NDP}MFRRUp_{j,t_i} +\sum_{j\in NDC} MFRRUp_{j,t_i}=MFRRUpTot_{t_i}$$
$$\sum_{j\in D}MFRRDown_{j,t_i}+\sum_{j\in NDP}MFRRDown_{j,t_i} +\sum_{j \in NDC} MFRRDown_{j,t_i}=MFRRDownTot_{t_i}$$
$$\sum_{j\in D}
RRUp_{j,t_i}+\sum_{j\in NDP} RRUp_{j,t_i} +\sum_{j \in NDC} RRUp_{j,t_i}= RRUpTot_{t_i}$$
$$\sum_{j\in D} RRDown_{j,t_i}+\sum_{j\in NDP} RRDown_{j,t_i} +\sum_{j \in NDC} RRDown_{j,t_i} = RRDownTot_{t_i}$$

The imbalance is also constraining and can’t pass a certain limit:

$$SmallImbalUp_{t_i}+LargeImbalUp_{t_i} = MaxOverallImbal_{t_i}$$
$$SmallImbalDown_{t_i}+LargeImbalDown_{t_i} = MaxOverallImbal_{t_i}$$

## Thermal constraints

The thermal constrains are the same as in “DayAhead Orders” module.

## Hydraulic constraints
This section details constraints for hydraulic Equipments. Those constraints are inspired from “DayAhead Orders”.
The sum of the power delivered by the different hydraulic fragments must be equal to the power of each fragment:
$$
PowerLevel_{t_i} = \sum_{n=0}^{nbfrag} PowerLevelFragment_{t_i,n}
$$
$$
MinimumPower_{t_i} \le PowerLevel_{t_i} \le MaximumPower{t_i}
$$

## Storage constraints
The storage constraints are the same as in “DayAhead Orders” module.

 **1. A storage equipment must respect maximum and minimum power constraints:**

$$
 Pv_{t_i}  + AFRRUp_{j,t_i} + MFRRUp_{j,t_i} + RRUp_{j,t} \le isV2G*Pmax_{t_i} * \frac{\Delta T}{60} *Rdisch*isSell_t
$$
$$
Pa_t-AFRRDown_{j,t_i}-MFRRDown_{j,t_i}-RRDown_{j,t_i} \ge (1- isSell_t)*-Pmax_t * \frac{\Delta T}{60}
$$

**2. For Electrical Vehicles, the maximum power depends on the state of charge**
$$-Pa_{t_0} +AFRRDown_{j,t_0}+MFRRDown_{j,t_0}+RRDown_{j,t_0} \le  \frac{Pmax{t_0}} {1-MinimumStateOfCharge} *\frac{InitialStock}{Emax_{t_0 } }$$
$$-Pa_t+AFRRDown_{j,t_i}+MFRRDown_(j,t_i )+RRDown_{j,ti} \le \frac{Pmax{t_0}} {1-MinimumStateOfCharge} * \frac{StoredEnergy_{t-1}}{Emax_t}$$
$ t_0 <  t < t_{f_{Op} } $
**3. Stock management**
The stock of each Equipment at instant t can be expressed with the following equation:
$$StoredEnergy_{t_0}=InitialStock + Qa_{t_0}*R_{ch}-\frac{Qv_{t_0}}{R_{disch}}   + (Emax_{t_1}-Emax_{t_0})-(Edisp{t_1}-Edisp{t_0})$$
$$ StoredEnergy_t=StoredEnergy_{t-1}+Qa_t*R_ {ch}-\frac{Qv_t}{R_{disch}}   +(Emax_{t+1}-Emax_t)-(Edisp_{t+1}-Edisp_t) $$
$t_0 < t < t_{f_{Op}}$
**4. Maximum capacity**
$$ 	StoredEnergy= MinimumStateOfCharge*Emax$$
$$ StoredEnergy_t \le Emax $$
$t_0 < t < t_{f_{Op}}$
**5. Additional period**

$$ Qv_{t}=\sum_{n=0}^{PowerFragments-1} Qv_{n,t}$$
$$ Qa_{t}=\sum_{n=0}^{PowerFragments-1} Qa_{n,t}$$
$$ Qv_{n,t} \le \frac{P_{max_t}}{PowerFragments}$$
$$ Qa_{n,t} \le \frac{P_{max_t}}{PowerFragments}$$
$t_0 < t < t_{f_{Op}}$

## Wind and Photovoltaic constraints
This section details constraints applied to Wind and Photovoltaic Equipments.
The power output of these Equipments must be within the following bounds, where $t\in T_{OP}$ and $t_{exec}$ is the *ExecutionDate*.
$$
MaximumPowerForecast_{t_{exec},t} * (1 - MaximumCurtailmentRatio_{t}) \le PowerLevel_{t} \le MaximumPowerForecast_{t_{exec},t}
$$

# Output
The main output is the Power provided by each Equipment at each time step of the optimization period. The module stores output in the following way:
- A new column in Power forecast matrix, corresponding to *ExecutionDate*, and storing the Power output for all Equipments except for Non dispatchable Equipments.
- A new column in StoredEnergy forecast matrix, corresponding to *ExecutionDate*, for Hydraulic and Storage Equipments, storing the new storage level calculated after Power level modifications.
