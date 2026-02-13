from abc import ABC, abstractmethod
from typing import Any

import atlas.config as cfg
from atlas import BusinessModel
from atlas.enums import BusinessModelName


class ChangeSet(ABC):
    def __init__(self, model_type: type[BusinessModel] | BusinessModelName):
        self.model_type = self.get_model_type(model_type)

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize the ChangeSet"""
        pass

    @staticmethod
    def check_data(data: dict[str, Any]):
        if "name" not in data:
            raise KeyError("'name' should be in data")

    @staticmethod
    def get_model_type(model_type: type[BusinessModel] | BusinessModelName) -> BusinessModelName:
        if isinstance(model_type, type) and issubclass(model_type, BusinessModel):
            model_type = cfg.INVERSE_MODEL_MAPPING_NAME[model_type]
        return model_type


class AddObject(ChangeSet):
    def __init__(self, data: dict[str, Any], model_type: type[BusinessModel] | BusinessModelName):
        super().__init__(model_type)
        self.check_data(data)
        self.data = data

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(obj.__dict__, type(obj))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "add", "data": self.data}


class UpdateObject(ChangeSet):
    def __init__(self, data: dict[str, Any], model_type: type[BusinessModel] | BusinessModelName):
        super().__init__(model_type)
        self.check_data(data)
        self.data = data
        self.model_type = self.get_model_type(model_type)

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(obj.__dict__, type(obj))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "update", "data": self.data}


class DeleteObject(ChangeSet):
    def __init__(self, name: str, model_type: type[BusinessModel] | BusinessModelName):
        super().__init__(model_type)
        self.name = name
        self.model_type = self.get_model_type(model_type)

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(obj.name, type(obj))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "delete", "name": self.name}
