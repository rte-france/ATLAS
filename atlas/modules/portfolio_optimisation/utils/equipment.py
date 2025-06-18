from atlas.modules.portfolio_optimisation.enum import EquipmentType


class EquipmentClassifier:
    """Handles equipment classification and filtering."""

    def __init__(self, parameters):
        self.parameters = parameters

    def is_excluded_technology(self, equipment) -> bool:
        """Check if equipment technology is excluded."""
        return equipment.Class in self.parameters.excluded_technologies

    def is_excluded_thermal_strategy(self, equipment) -> bool:
        """Check if thermal equipment strategy is excluded."""
        return hasattr(equipment, "Strategy") and equipment.Strategy in self.parameters.excluded_thermal_strategies

    def is_excluded_market_area(self, portfolio) -> bool:
        """Check if portfolio market area is excluded."""
        return not self.parameters.use_forecast and portfolio.MarketArea.Name in self.parameters.excluded_market_areas

    def should_manually_activate(self, equipment) -> bool:
        """Determine if equipment should be manually activated."""
        return self.is_excluded_technology(equipment) or self.is_excluded_thermal_strategy(equipment)


class EquipmentCollector:
    """Collects and organizes equipment by type."""

    def __init__(self):
        self.equipment_by_type: dict[EquipmentType, list] = {equipment_type: [] for equipment_type in EquipmentType}

    def add_equipment(self, equipment_type: EquipmentType, equipment):
        """Add equipment to the appropriate collection."""
        self.equipment_by_type[equipment_type].append(equipment)

    def get_equipment(self, equipment_type: EquipmentType) -> list:
        """Get equipment list for a specific type."""
        return self.equipment_by_type[equipment_type]

    def clear(self):
        """Clear all equipment collections."""
        for equipment_list in self.equipment_by_type.values():
            equipment_list.clear()
