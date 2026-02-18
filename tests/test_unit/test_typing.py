from typing import get_args, get_origin

import atlas.type as atlas_typing


class DummyReferenced:
    pass


class DummyModel:
    model_fields = {
        "int_attr": type("Field", (), {"annotation": int}),
        "float_attr": type("Field", (), {"annotation": float}),
        "str_attr": type("Field", (), {"annotation": str}),
        "union_attr": type("Field", (), {"annotation": int | None}),
        "list_attr": type("Field", (), {"annotation": list[str]}),
        "referenced_attr": type("Field", (), {"annotation": DummyReferenced}),
        "list_referenced_attr": type("Field", (), {"annotation": list[DummyReferenced]}),
    }


class DummyConfig:
    MODEL_MAPPING_NAME = {"dummy": type("Dummy", (), {"model_fields": DummyModel.model_fields})}


_original_model_mapping_name = None


def setup_module(module):
    global _original_model_mapping_name
    _original_model_mapping_name = atlas_typing.cfg.MODEL_MAPPING_NAME
    atlas_typing.cfg.MODEL_MAPPING_NAME = DummyConfig.MODEL_MAPPING_NAME


def teardown_module(module):
    atlas_typing.cfg.MODEL_MAPPING_NAME = _original_model_mapping_name


def test_get_type_attribute_int():
    assert atlas_typing.get_type_attribute("dummy", "int_attr") is int


def test_get_type_attribute_float():
    assert atlas_typing.get_type_attribute("dummy", "float_attr") is float


def test_get_type_attribute_str():
    assert atlas_typing.get_type_attribute("dummy", "str_attr") is str


def test_get_type_attribute_union():
    result = atlas_typing.get_type_attribute("dummy", "union_attr")

    assert result is int


def test_get_type_attribute_list():
    result = atlas_typing.get_type_attribute("dummy", "list_attr")

    assert get_origin(result) is list
    assert get_args(result)[0] is str


def test_get_type_attribute_referenced():
    result = atlas_typing.get_type_attribute("dummy", "referenced_attr")

    assert result is DummyReferenced


def test_get_type_attribute_list_referenced():
    result = atlas_typing.get_type_attribute("dummy", "list_referenced_attr")

    assert get_origin(result) is list
    assert get_args(result)[0] is DummyReferenced
