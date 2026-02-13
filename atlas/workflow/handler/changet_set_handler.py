from typing import Any

import atlas.config as cfg
from atlas.models.business_model import BusinessModel
from atlas.typing import get_type_attribute
from atlas.workflow.change_set import AddObject, ChangeSet, DeleteObject, UpdateObject
from atlas.workflow.current_input_state import CurrentInputState


class ChangeSetHandler:
    @staticmethod
    def apply(change_set: ChangeSet, cis: CurrentInputState):
        if isinstance(change_set, AddObject):
            ChangeSetHandler._add(change_set, cis)

        elif isinstance(change_set, UpdateObject):
            ChangeSetHandler._update(change_set, cis)

        elif isinstance(change_set, DeleteObject):
            ChangeSetHandler._remove(change_set, cis)

        else:
            raise TypeError(f"Unsupported ChangeSet {type(change_set)}")

    @staticmethod
    def _add(change_set: AddObject, cis: CurrentInputState):
        """
        Add an object to the correct container in CurrentInputState.
        The container is determined dynamically based on the type of the object.
        Find the BusinessModel of the attribute in the other cis container
        """
        data = change_set.data.copy()  # avoid mutating original
        obj = change_set.model_type.model_validate({"name": data["name"]})

        ChangeSetHandler._resolve_reference(obj, data, cis)
        ChangeSetHandler._fill_object(obj, data)

        container = cis.data.get_container_by_type(change_set.model_type)

        # Add the object to the container
        container.add(obj)

    @staticmethod
    def _update(change_set: UpdateObject, cis: CurrentInputState):
        """
        Update an existing object in the correct container in CurrentInputState.
        References to other BusinessModel objects are resolved automatically.
        Find the BusinessModel of the attribute in the other cis container
        """
        data = change_set.data.copy()  # avoid mutating original
        container = cis.data.get_container_by_type(change_set.model_type)

        # Get the existing object by name
        obj_name = data.get("name")
        try:
            obj: BusinessModel = container.get(obj_name)
        except KeyError:
            raise ValueError(
                f"Object '{obj_name}' not found in container for type {change_set.model_type.__name__}"
            ) from None

        ChangeSetHandler._resolve_reference(obj, data, cis)
        ChangeSetHandler._fill_object(obj, data)

    @staticmethod
    def _resolve_reference(obj: BusinessModel, data: dict[str, Any], cis: CurrentInputState):
        # Resolve BusinessModel references in data
        for key, value in data.items():
            if key == "name":
                continue  # do not update the name

            if isinstance(value, BusinessModel):
                # Already an instance, see if it exists in CIS
                ref_container = cis.data.get_container_by_type(type(value))
                try:
                    existing = ref_container.get(value.name)
                    data[key] = existing
                except KeyError:
                    raise ValueError(
                        f"Trying to update '{obj.__class__}' attribute '{key}' "
                        f"with '{value.name}' but it is not present in CurrentInputState"
                    ) from None

            elif isinstance(value, str):
                attr_type = get_type_attribute(cfg.INVERSE_MODEL_MAPPING_NAME[obj.__class__], key)
                if attr_type and isinstance(attr_type, type) and issubclass(attr_type, BusinessModel):
                    ref_container = cis.data.get_container_by_type(attr_type)
                    try:
                        existing = ref_container.get(value)
                        data[key] = existing
                    except KeyError:
                        raise ValueError(
                            f"Trying to update '{obj.__class__}' attribute '{key}' "
                            f"with '{value}' but it is not present in CurrentInputState"
                        ) from None

    @staticmethod
    def _fill_object(obj: BusinessModel, data: dict[str, Any]):
        for key, value in data.items():
            if key == "name":
                continue  # do not update the name
            setattr(obj, key, value)

    @staticmethod
    def _remove(change_set: DeleteObject, cis: CurrentInputState):
        container = cis.data.get_container_by_type(change_set.model_type)
        if change_set.name not in container:
            raise ValueError(
                f"Trying to remove '{change_set.model_type}' object '{change_set.name}' "
                f"but it is not present in CurrentInputState"
            )
        container.remove(change_set.name)
