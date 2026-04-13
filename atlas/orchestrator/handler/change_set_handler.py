from typing import Any, cast

from pydantic import ValidationError

import atlas.config as cfg
from atlas.config import logger
from atlas.objects.business_model import BusinessModel
from atlas.orchestrator.change_set import AddObject, ChangeSet, DeleteObject, UpdateObject
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.type import get_type_attribute


class ChangeSetHandler:
    @staticmethod
    def apply(change_set: ChangeSet, cis: CurrentInputState):
        """Apply a single change set to the current input state.

        :param change_set: The change set to apply
        :type change_set: ChangeSet
        :param cis: The current input state to modify
        :type cis: CurrentInputState

        """
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
        obj_name = data.get("name")

        # Validate that the object doesn't already exist
        container = cis.data.get_container_by_type(change_set.model_type)
        if obj_name in container:
            raise ValueError(
                f"Cannot add '{change_set.model_type}' object '{obj_name}': "
                f"an object with this name already exists in CurrentInputState"
            )

        # Validate model class exists
        model_class = cfg.MODEL_MAPPING_NAME.get(change_set.model_type)
        if model_class is None:
            raise ValueError(f"Unknown model type: {change_set.model_type}")

        logger.debug(f"Adding new {change_set.model_type} object: {obj_name}")

        # Resolve references before creating the object (needed for required fields)
        ChangeSetHandler._resolve_reference(data, cis, model_class=model_class)

        # Create object with all data after references are resolved
        try:
            obj = model_class.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"Invalid data for {change_set.model_type} object '{obj_name}': {e}") from e

        # Add the object to the container
        container.add(obj)
        logger.debug(f"Successfully added {change_set.model_type} object: {obj_name}")

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
        if not obj_name:
            raise ValueError(f"UpdateObject for {change_set.model_type} is missing 'name' field")

        logger.debug(f"Updating {change_set.model_type} object: {obj_name}")

        try:
            obj: BusinessModel = container.get(str(obj_name))
        except KeyError:
            raise ValueError(
                f"Cannot update '{change_set.model_type}' object '{obj_name}': object not found in CurrentInputState"
            ) from None

        # Validate that we're only updating existing fields (optional but recommended)
        # This can be relaxed if dynamic field addition is needed
        model_class = cfg.MODEL_MAPPING_NAME.get(change_set.model_type)
        if model_class is not None:
            model_fields = model_class.model_fields.keys()
            invalid_fields = [key for key in data.keys() if key not in model_fields and key != "name"]
            if invalid_fields:
                logger.warning(f"Updating {change_set.model_type} '{obj_name}' with non-model fields: {invalid_fields}")

        ChangeSetHandler._resolve_reference(data, cis, obj=obj)
        ChangeSetHandler._fill_object(obj, data)
        logger.debug(f"Successfully updated {change_set.model_type} object: {obj_name}")

    @staticmethod
    def _resolve_reference(
        data: dict[str, Any],
        cis: CurrentInputState,
        model_class: type[BusinessModel] | None = None,
        obj: BusinessModel | None = None,
    ):
        """Resolve BusinessModel references in data.

        Can be used either with a model_class (for static resolution during object creation)
        or with an obj instance (for resolution during object updates).

        :param data: Dictionary containing the data to resolve references in
        :param cis: Current input state containing the reference objects
        :param model_class: Model class for static resolution (used in AddObject)
        :param obj: Object instance for resolution (used in UpdateObject)
        :raises ValueError: If neither model_class nor obj is provided, or if references are invalid
        """
        if model_class is None and obj is None:
            raise ValueError("Either model_class or obj must be provided")

        # Determine which class to use for type lookup
        target_class = cast(type[BusinessModel], model_class if model_class is not None else obj.__class__)
        # Determine operation type for error messages
        operation = "set" if model_class is not None else "update"

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
                        f"Trying to {operation} '{target_class}' attribute '{key}' "
                        f"with '{value.name}' but it is not present in CurrentInputState"
                    ) from None

            elif isinstance(value, str):
                attr_type = get_type_attribute(cfg.INVERSE_MODEL_MAPPING_NAME[target_class], key)
                if attr_type and isinstance(attr_type, type) and issubclass(attr_type, BusinessModel):
                    ref_container = cis.data.get_container_by_type(attr_type)
                    try:
                        existing = ref_container.get(value)
                        data[key] = existing
                    except KeyError:
                        raise ValueError(
                            f"Trying to {operation} '{target_class}' attribute '{key}' "
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
        """Remove an object from the CurrentInputState.

        :param change_set: The delete change set
        :param cis: The current input state
        :raises ValueError: If the object doesn't exist
        """
        logger.debug(f"Removing {change_set.model_type} object: {change_set.name}")

        container = cis.data.get_container_by_type(change_set.model_type)
        if change_set.name not in container:
            raise ValueError(
                f"Cannot remove '{change_set.model_type}' object '{change_set.name}': "
                f"object not found in CurrentInputState"
            )
        container.remove(change_set.name)
        logger.debug(f"Successfully removed {change_set.model_type} object: {change_set.name}")
