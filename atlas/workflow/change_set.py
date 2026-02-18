from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import atlas.config as cfg
from atlas import BusinessModel
from atlas.enums import BusinessModelName


class ChangeSet(ABC):
    kind: ClassVar[str]

    def __init__(self, model_type: type[BusinessModel] | BusinessModelName | str):
        self.model_type = self.get_model_type(model_type)

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize the ChangeSet"""

    @classmethod
    def from_object(cls, obj: BusinessModel) -> ChangeSet:
        """Factory method to build a ChangeSet from a BusinessModel."""
        model_type = type(obj)
        return cls._build_from_obj(obj, model_type)

    @classmethod
    @abstractmethod
    def _build_from_obj(
        cls,
        obj: BusinessModel,
        model_type: type[BusinessModel],
    ) -> ChangeSet:
        """Subclass-specific object conversion."""

    @staticmethod
    def get_model_type(
        model_type: type[BusinessModel] | BusinessModelName | str,
    ) -> BusinessModelName:
        if isinstance(model_type, BusinessModelName):
            return model_type

        if isinstance(model_type, type):
            if not issubclass(model_type, BusinessModel):
                raise TypeError(f"{model_type} is not a subclass of BusinessModel")

            for cls in model_type.__mro__:
                if cls in cfg.INVERSE_MODEL_MAPPING_NAME:
                    return cfg.INVERSE_MODEL_MAPPING_NAME[cls]
            raise ValueError(
                f"Model class {model_type.__name__} has no registered ancestor in INVERSE_MODEL_MAPPING_NAME"
            )

        if isinstance(model_type, str):
            return BusinessModelName(model_type.lower())

        raise TypeError(
            f"Invalid model_type: {model_type!r}. Expected BusinessModel subclass, BusinessModelName, or string."
        )


class AddObject(ChangeSet):
    kind = "add"

    def __init__(self, data: dict[str, Any], model_type):
        super().__init__(model_type)
        self._validate_data(data)
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "data": self.data}

    @classmethod
    def _build_from_obj(cls, obj: BusinessModel, model_type):
        return cls(obj.__dict__.copy(), model_type)

    @staticmethod
    def _validate_data(data):
        if "name" not in data:
            raise KeyError("AddObject requires 'name' in data")


class UpdateObject(ChangeSet):
    kind = "update"

    def __init__(self, data: dict[str, Any], model_type):
        super().__init__(model_type)
        self._validate_data(data)
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "data": self.data}

    @classmethod
    def _build_from_obj(cls, obj: BusinessModel, model_type):
        return cls(obj.__dict__.copy(), model_type)

    @staticmethod
    def _validate_data(data):
        if "name" not in data:
            raise KeyError("UpdateObject requires 'name' in data")


class DeleteObject(ChangeSet):
    kind = "delete"

    def __init__(self, name: str, model_type):
        super().__init__(model_type)
        self.name = name

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "name": self.name}

    @classmethod
    def _build_from_obj(cls, obj: BusinessModel, model_type):
        return cls(obj.name, model_type)
