import json
from pathlib import Path

import pytest
import yaml

from could_you.dynamic import Dynamic


def test_init_from_kwargs_and_dict():
    d = Dynamic({"foo": 1}, bar=2)
    assert d.foo == 1
    assert d.bar == 2
    d2 = Dynamic(foo=1, bar=2)
    assert d2.foo == 1
    assert d2.bar == 2
    d3 = Dynamic({"nested": {"x": 10}})
    assert isinstance(d3.nested, Dynamic)
    assert d3.nested.x == 10


def test_init_object_with___dict__():
    class Dummy:
        def __init__(self):
            self.apple = 42

    dummy = Dummy()
    d = Dynamic(dummy)
    assert d.apple == 42


def test_list_set_tuple_recursion():
    d = Dynamic({"lst": [{"x": 1}, {"y": 2}], "tpl": ({"z": 3},)})
    assert isinstance(d.lst[0], Dynamic)
    assert d.lst[1].y == 2
    assert isinstance(d.tpl[0], Dynamic)
    assert d.tpl[0].z == 3

class Thing(Dynamic):
    name: str
    number: int

class ClassWithTypedList(Dynamic):
    a_list: list
    some_list: list[Thing]
    some_set: set[str]
    some_tuple: tuple[Thing]

def test_typed_array_collection():
    c = ClassWithTypedList(
            a_list=["a", 2, False],
            some_list=[dict(name="name", number=1)],
            some_set=["1", 2, "2"],
            some_tuple=[dict(name="name2", number=2)])

    assert c.a_list == ["a", 2, False]
    assert len(c.some_list) == 1
    assert type(c.some_list[0]) == Thing
    assert len(c.some_set) == 2
    assert type(c.some_set) == set
    assert c.some_set == {"1", "2"}
    assert len(c.some_tuple) == 1
    assert type(c.some_tuple[0]) == Thing
    assert c.some_tuple[0].name == "name2"

def test_getattr_snake_case_to_camelCase():  # noqa: N802
    d = Dynamic(camelCaseAttr=5)
    assert d.camel_case_attr == 5
    assert d.camelCaseAttr == 5
    assert d.unknown_attr is None


def test_to_dict_handles_nested_Dynamic_and_Path():  # noqa: N802
    d = Dynamic(foo=Path("/abc/def"), sub=Dynamic(bar=33))
    dct = d.to_dict()
    assert isinstance(dct["foo"], str)
    assert dct["foo"] == "/abc/def"
    assert isinstance(dct["sub"], dict)
    assert dct["sub"]["bar"] == 33


def test_dumps_json_and_yaml():
    d = Dynamic(x=1, y=2)
    json_str = d.dumps("json")
    yaml_str = d.dumps("yaml")
    assert isinstance(json.loads(json_str), dict)
    loaded = yaml.safe_load(yaml_str)
    assert loaded["x"] == 1
    assert loaded["y"] == 2


def test_load_json_yaml_and_fallback_warn(tmp_dir, caplog):
    # Uses tmp_dir fixture from conftest for temp file/directory
    data = {"alpha": 123, "beta": {"x": "y"}}
    jpath = tmp_dir / "test.json"
    ypath = tmp_dir / "test.yaml"
    upath = tmp_dir / "test.any"
    with open(jpath, "w") as f:
        json.dump(data, f)
    with open(ypath, "w") as f:
        yaml.dump(data, f)
    with open(upath, "w") as f:
        yaml.dump(data, f)
    djson = Dynamic.load(jpath)
    dyaml = Dynamic.load(ypath)
    caplog.set_level("WARNING")
    dany = Dynamic.load(upath)
    assert djson.to_dict() == data
    assert dyaml.to_dict() == data
    assert dany.to_dict() == data
    assert f"Unrecognized file extension .any in {upath}" in caplog.text


a = Dynamic(a="a", c="a", l=["a"], nested=dict(na="na"))
b = Dynamic(b="b", c="b", l=["b"], nested=dict(nb="nb"))
ab = dict(a="a", b="b", c="b", l=["b"], nested=dict(na="na", nb="nb"))
ba = dict(a="a", b="b", c="a", l=["a"], nested=dict(na="na", nb="nb"))


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (a, b, ab),
        (b, a, ba),
        (a.to_dict(), b, ab),
        (a, b.to_dict(), ab),
    ],
)
def test_various_params(left, right, expected):
    result = left | right
    assert result.to_dict() == expected
