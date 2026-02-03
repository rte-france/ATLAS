from abc import ABC, abstractmethod
from typing import Any

from atlas import BusinessModel


class ChangeSet(ABC):
    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize the ChangeSet"""
        pass


# TODO : name must be present !
class AddObject(ChangeSet):
    def __init__(self, data: dict[str, Any], model_type: type[BusinessModel]):
        self.data = data
        self.model_type = model_type  # type inferred from obj

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(obj.__dict__, type(obj))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "add", "data": self.data}


class UpdateObject(ChangeSet):
    def __init__(self, data: dict[str, Any], model_type: type[BusinessModel]):
        self.data = data
        self.model_type = model_type

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(obj.__dict__, type(obj))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "update", "data": self.data}


class DeleteObject(ChangeSet):
    def __init__(self, name: str, model_type: type[BusinessModel]):
        self.name = name
        self.model_type = model_type

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(obj.name, type(obj))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "delete", "name": self.name}
