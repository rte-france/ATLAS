"""Day-Ahead Orders — thermal bidding pipeline.

Public entry point for the rest of the module pipeline.
"""

from atlas.modules.day_ahead_orders.steps.thermal.bidding import ThermalBidding

__all__ = ["ThermalBidding"]
