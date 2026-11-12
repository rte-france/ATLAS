import pytest

from atlas.abstract_class.module import AbstractModule
from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.orchestrator.module_registry import ModuleRegistry


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

    def test_every_module_gives_its_parameters_class_without_an_instance(self):
        """The CLI reads the parameters class of the module class, before building any instance."""
        for member in ModuleRegistry:
            assert issubclass(member.value.get_parameters_class(), AbstractModuleParameters), member.name
