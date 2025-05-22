import pytest

import atlas.typing as atlas_typing


class DummyModel:
    model_fields = {
        "int_attr": type("Field", (), {"annotation": int}),
        "float_attr": type("Field", (), {"annotation": float}),
        "str_attr": type("Field", (), {"annotation": str}),
        "union_attr": type("Field", (), {"annotation": int | None}),
    }


class DummyConfig:
    MODEL_MAPPING_NAME = {"dummy": type("Dummy", (), {"model_fields": DummyModel.model_fields})}


def setup_module(module):
    atlas_typing.cfg.MODEL_MAPPING_NAME = DummyConfig.MODEL_MAPPING_NAME


def test_get_type_attribute_int():
    assert atlas_typing.get_type_attribute("dummy", "int_attr") is int


def test_get_type_attribute_float():
    assert atlas_typing.get_type_attribute("dummy", "float_attr") is float


def test_get_type_attribute_str():
    assert atlas_typing.get_type_attribute("dummy", "str_attr") is str


def test_get_type_attribute_union():
    result = atlas_typing.get_type_attribute("dummy", "union_attr")
    # Should return int (the first type in the union)
    assert result is int


def test_get_type_attribute_invalid_object_type():
    with pytest.raises(ValueError):
        atlas_typing.get_type_attribute("not_a_type", "int_attr")


def test_get_type_attribute_invalid_attribute():
    with pytest.raises(KeyError):
        atlas_typing.get_type_attribute("dummy", "not_an_attr")
