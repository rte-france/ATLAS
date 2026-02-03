from types import UnionType
from typing import Union, get_args, get_origin

from atlas.models.business_model import BusinessModel
from atlas.workflow.change_set.change_set import AddObject, ChangeSet, DeleteObject, UpdateObject
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

        # Resolve any BusinessModel references
        for key, value in data.items():
            if isinstance(value, BusinessModel):
                # Already an instance, see if it exists in CIS
                existing = cis.data.get_container_by_type(type(value)).get(value.name)
                if existing:
                    data[key] = existing
                else:
                    raise ValueError(
                        f"Trying to add a '{change_set.model_type}' but '{key}' of value '{value.name}' is not present"
                    )
            elif isinstance(value, str):
                # Sometimes the data may just contain a name for a reference
                # Try to find a BusinessModel container matching the type annotation
                attr_type = getattr(change_set.model_type, "__annotations__", {}).get(key)
                attr_type = ChangeSetHandler.resolve_type(attr_type)
                if attr_type and isinstance(attr_type, type) and issubclass(attr_type, BusinessModel):
                    try:
                        existing = cis.data.get_container_by_type(attr_type).get(value)
                        data[key] = existing
                    except KeyError:
                        raise ValueError(
                            f"Trying to add a '{change_set.model_type}' but '{key}' of value '{value}' "
                            f"can't be retrieve"
                        )

        # Instantiate the object from the data
        obj: BusinessModel = change_set.model_type(**data)

        # Map model type to dataset attribute
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

        # First, get the container corresponding to the model type
        container = cis.data.get_container_by_type(change_set.model_type)

        # Get the existing object by name
        obj_name = data.get("name")
        try:
            obj: BusinessModel = container.get(obj_name)
        except KeyError:
            raise ValueError(f"Object '{obj_name}' not found in container for type {change_set.model_type.__name__}")

        # Resolve BusinessModel references in data
        for key, value in data.items():
            if key == "name":
                continue  # do not update the name

            if isinstance(value, BusinessModel):
                # Already an instance, see if it exists in CIS
                ref_container = cis.data.get_container_by_type(type(value))
                existing = ref_container.get(value.name)
                data[key] = existing

            elif isinstance(value, str):
                # Maybe a name referring to another BusinessModel
                attr_type = getattr(change_set.model_type, "__annotations__", {}).get(key)
                attr_type = ChangeSetHandler.resolve_type(attr_type)
                if attr_type and isinstance(attr_type, type) and issubclass(attr_type, BusinessModel):
                    ref_container = cis.data.get_container_by_type(attr_type)
                    try:
                        existing = ref_container.get(value)
                        data[key] = existing
                    except KeyError:
                        raise ValueError(
                            f"Trying to update '{change_set.model_type.__name__}' attribute '{key}' "
                            f"with '{value}' but it is not present in CurrentInputState"
                        )

        # Apply updates to the object
        for key, value in data.items():
            if key != "name":
                setattr(obj, key, value)

    @staticmethod
    def _remove(change_set: DeleteObject, cis: CurrentInputState):
        cis.data.order.remove(change_set.name)

    @staticmethod
    def resolve_type(attr_type):
        origin = get_origin(attr_type)
        if origin is Union or origin is UnionType:
            args = [a for a in get_args(attr_type) if a is not type(None)]
            if args:
                return args[0]
        return attr_type
