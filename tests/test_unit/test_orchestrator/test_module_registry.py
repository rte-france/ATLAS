import pytest

from atlas.core.abstract_class.module import AbstractModule
from atlas.core.orchestrator.module_registry import ModuleRegistry
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule


class TestModuleRegistry:
    def test_get_known_module_returns_class(self):
        cls = ModuleRegistry.get("PortfolioOptimisation")
        assert cls is PortfolioOptimisationModule

    def test_get_unknown_module_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown module"):
            ModuleRegistry.get("NonExistentModule")

    def test_all_registry_entries_are_abstract_module_subclasses(self):
        for member in ModuleRegistry:
            assert issubclass(member.value, AbstractModule)
