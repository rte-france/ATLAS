"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC, abstractmethod
from typing import Any, Type

from atlas import BusinessModel
from atlas.config import INVERSE_MODEL_MAPPING_NAME, MODEL_MAPPING_NAME


class ChangeSet(ABC):
    @abstractmethod
    def apply(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]) -> None:
        pass

    @abstractmethod
    def rollback(self, list_bmo: dict[str, dict[str, Any]]) -> None:
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize the ChangeSet"""
        pass


class AddObject:
    def __init__(self, type: str, data: dict[str, Any]):
        self.type = type
        self.data = data
        self._backup_name = self.data["name"]

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(INVERSE_MODEL_MAPPING_NAME[obj.__class__], obj.__dict__)

    def apply(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]):
        if self.data["name"] in list_bmo[self.type]:
            raise KeyError("Object already exists")

        list_bmo[self.type][self.data["name"]] = MODEL_MAPPING_NAME[self.type].model_validate(self.data)

    def rollback(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]):
        del list_bmo[self.type][self._backup_name]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "add", "type": self.type, "data": self.data, "_backup_name": self._backup_name}


class UpdateObject(ChangeSet):
    def __init__(self, type: str, name: str, data: dict[str, Any]):
        self.name = name
        self.type = type
        self.data = data
        self._backup_data = None

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(INVERSE_MODEL_MAPPING_NAME[obj.__class__], obj.name, obj.__dict__)

    def apply(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]):
        if self.name not in list_bmo[self.type]:
            raise KeyError("Object doesn't exists")

        obj = list_bmo[self.type][self.name]
        self._backup_data = obj.model_dump(mode="json")
        for key, value in self.data.items():
            setattr(obj, key, value)

        # if we have changed the name
        if self.name != obj.name:
            del list_bmo[self.type][self.name]
            list_bmo[self.type][obj.name] = obj

    def rollback(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]):
        obj = list_bmo[self.type][self.data["name"]]
        for k, v in self._backup_data.items():
            setattr(obj, k, v)

        # if we have changed the name
        if self.name != self.data["name"]:
            del list_bmo[self.type][self.data["name"]]
            list_bmo[self.type][self.name] = obj

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "update",
            "type": self.type,
            "name": self.name,
            "data": self.data,
            "_backup_data": self._backup_data,
        }


class DeleteObject(ChangeSet):
    def __init__(self, type: str, name):
        self.type = type
        self.name = name
        self._backup = None

    @classmethod
    def from_obj(cls, obj: BusinessModel):
        return cls(INVERSE_MODEL_MAPPING_NAME[obj.__class__], obj.name)

    def apply(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]):
        if self.name not in list_bmo[self.type]:
            raise KeyError("Object doesn't exist")
        self._backup = list_bmo[self.type][self.name]
        del list_bmo[self.type][self.name]

    def rollback(self, list_bmo: dict[str, dict[str, type[BusinessModel]]]):
        list_bmo[self.type][self.name] = self._backup

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "delete", "type": self.type, "name": self.name, "_backup": self._backup}
