import pytest

from atlas.io_utils.container import Container
from atlas.models.business_model import BusinessModel


class DummyBM(BusinessModel):
    def __init__(self, name: str):
        super().__init__(name=name)


def test_container_init_empty():
    c = Container()
    assert len(c) == 0
    assert c.is_empty()
    assert not c


def test_container_init_with_items():
    items = [DummyBM("a"), DummyBM("b")]
    c = Container(items)

    assert len(c) == 2
    assert not c.is_empty()


def test_container_add_unique():
    c = Container()
    item = DummyBM("a")

    c.add(item)

    assert len(c) == 1
    assert c.get("a") is item


def test_container_add_wrong_type_raises_type_error():
    class OtherBM(BusinessModel):
        def __init__(self, name: str):
            super().__init__(name=name)

    class DummyBMContainer(Container[DummyBM]):
        item_type = DummyBM

    c = DummyBMContainer()

    with pytest.raises(
        TypeError,
        match="Expected DummyBM, got OtherBM",
    ):
        c.add(OtherBM("x"))


def test_container_add_duplicate_raises():
    c = Container()
    c.add(DummyBM("a"))

    with pytest.raises(ValueError, match="Item with name 'a' already exists"):
        c.add(DummyBM("a"))


def test_container_get_existing():
    item = DummyBM("a")
    c = Container([item])

    assert c.get("a") is item


def test_container_get_missing_raises():
    c = Container([DummyBM("a")])

    with pytest.raises(KeyError, match="'b' not found"):
        c.get("b")


def test_container_remove_existing():
    c = Container([DummyBM("a"), DummyBM("b")])

    c.remove("a")

    assert len(c) == 1
    assert c.get("b").name == "b"


def test_container_remove_missing_is_noop():
    c = Container([DummyBM("a")])

    c.remove("missing")

    assert len(c) == 1


def test_container_all_returns_list():
    items = [DummyBM("a"), DummyBM("b")]
    c = Container(items)

    result = c.all()

    assert result == items


def test_container_clear():
    c = Container([DummyBM("a"), DummyBM("b")])

    c.clear()

    assert len(c) == 0
    assert c.is_empty()


def test_container_len_and_bool():
    c = Container()
    assert len(c) == 0
    assert not c

    c.add(DummyBM("x"))
    assert len(c) == 1
    assert c


def test_container_iter():
    items = [DummyBM("a"), DummyBM("b")]
    c = Container(items)

    names = [item.name for item in c]

    assert names == ["a", "b"]


def test_contains_string_key_present():
    a = DummyBM("a")
    c = Container([a])
    assert "a" in c


def test_contains_string_key_missing():
    a = DummyBM("a")
    c = Container([a])
    assert "b" not in c


def test_contains_object_present():
    a = DummyBM("a")
    c = Container([a])
    assert a in c


def test_contains_object_missing():
    a = DummyBM("a")
    b = DummyBM("b")
    c = Container([a])
    assert b not in c


def test_contains_unrelated_type():
    a = DummyBM("a")
    c = Container([a])
    assert 123 not in c
    assert None not in c
    assert [] not in c
