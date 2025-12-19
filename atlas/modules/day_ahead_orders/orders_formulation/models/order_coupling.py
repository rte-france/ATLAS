from atlas.enum import CouplingType
from atlas.models.market.order_coupling import OrderCoupling
from atlas.modules.day_ahead_orders.orders_formulation.models.order import OrderDAO


class OrderCouplingDAO(OrderCoupling):
    orders: list[OrderDAO] = []
    complement_energy: float = 0.0
    coupling_type: CouplingType
