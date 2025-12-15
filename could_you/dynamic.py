import inspect
import json
import re
import types
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import yaml

from .logging_config import LOGGER

_UNDEFINED = object()

def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return "".join(p.capitalize() if i > 0 else p for i, p in enumerate(parts))


_CAMEL_TO_SNAKE_PAT_1 = re.compile(r'([A-Z]+)([A-Z][a-z])')
_CAMEL_TO_SNAKE_PAT_2 = re.compile(r'(.)([A-Z][a-z]+)')
_CAMEL_TO_SNAKE_PAT_3 = re.compile(r'([a-z0-9])([A-Z])')


def camel_to_snake(name: str) -> str:
    """
    Convert a CamelCase or camelCase name to snake_case.

    Examples:
    - "camelCase" -> "camel_case"
    - "CamelCase" -> "camel_case"
    - "HTTPServer" -> "http_server"
    - "getHTTPResponseCode" -> "get_http_response_code"
    - "MyXMLParser2" -> "my_xml_parser2"
    """
    if not name:
        return name

    # Split between acronym sequences and a following Capital+lower (HTTPServer -> HTTP_Server)
    s = _CAMEL_TO_SNAKE_PAT_1.sub(r'\1_\2', name)
    # Split before groups like "MyClass" -> "My_Class"
    s = _CAMEL_TO_SNAKE_PAT_2.sub(r'\1_\2', s)
    # Split between lower-or-digit and Capital (myVar -> my_Var)
    s = _CAMEL_TO_SNAKE_PAT_3.sub(r'\1_\2', s)
    # Replace dashes (if any) and lowercase the result
    return s.replace('-', '_').lower()


class DynamicMeta(type):
    def __getattr__(cls, attr: str) -> Any:
        # Convert snake_case to camelCase
        camel = snake_to_camel(attr)
        # Look in the class dict (bypass normal lookup, so we must handle descriptors)
        val = cls.__dict__.get(camel, _UNDEFINED)

        if val is not _UNDEFINED:
            # If it's a descriptor, bind for class access
            if get := getattr(val, "__get__", None):
                return get(None, cls)  # class-level binding

            return val

        return None

class Dynamic(metaclass=DynamicMeta):
    def __init__(self, input_dict: Any = None, **kwargs: dict[str, Any]) -> None:
        # Merge input_dict and kwargs, with kwargs taking precedence
        input_dict = input_dict or {}

        # If input_data is not a dictionary but has a __dict__, unpack it
        if hasattr(input_dict, "__dict__"):
            # assuming no __slots__
            input_dict = vars(input_dict)

        combined_data = {**input_dict, **kwargs}

        # Use setattr to set attributes from the dictionary
        for key, value in combined_data.items():
            new_value = self.__cast(key, value)
            setattr(self, key, new_value)

    def __cast(self, attr_name: str, value: Any):
        camel_name = camel_to_snake(attr_name)

        if attr_types := get_annotation_constructors(self.__class__, camel_name):
            if any(at is not Literal and isinstance(value, at) for at in attr_types):
                # no cast neccessary
                return value

            for at in attr_types:
                try:
                    return at(value)
                except Exception as ex:
                    LOGGER.debug(f"Could not cast {value} to {at}", ex)

        new_value = value

        if isinstance(value, dict):
            # If the value is a dictionary, convert it into another Dynamic instance
            new_value = Dynamic(value)

        elif hasattr(value, "__dict__"):
            # If the value has a __dict__, convert it into another Dynamic instance
            new_value = Dynamic(vars(value))

        elif isinstance(value, list | set | tuple):
            # If the value is a list, check for non-scalar values and convert them
            new_value = [
                Dynamic(item) if isinstance(item, dict) or hasattr(item, "__dict__") else item for item in value
            ]

        return new_value


    def __getattr__(self, attr: str) -> Any:
        camel = snake_to_camel(attr)

        # Check instance dict first
        if camel in self.__dict__:
            return self.__dict__[camel]

        # Let Python perform class-level lookup and descriptor binding
        try:
            return getattr(self.__class__, camel)
        except AttributeError as ae:
            raise AttributeError(f"Could not find value or default for attribute: {attr}") from ae

    @staticmethod
    def load(path: Path):
        if path.suffix == ".json":
            loader = json.load
        elif path.suffix in {".yaml", ".yml"}:
            loader = yaml.safe_load
        else:
            LOGGER.warning(f"Unrecognized file extension {path.suffix} in {path}, trying YAML")
            loader = yaml.safe_load

        with open(path) as file:
            return Dynamic(loader(file))

    def dumps(self, fmt: Literal["json", "yaml"] = "json") -> str:
        dumper = yaml.dump if fmt == "yaml" else json.dumps
        return dumper(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """
        Recursively converts the Dynamic object and its nested Dynamic instances
        back into a raw dictionary.
        """
        result = {}

        for key, value in self.__dict__.items():
            # If the value is another Dynamic instance, call to_dict on it
            if isinstance(value, Dynamic):
                result[key] = value.to_dict()
            # If the value is a list, process each item
            elif isinstance(value, list | set | tuple):
                result[key] = [item.to_dict() if isinstance(item, Dynamic) else item for item in value]
            elif isinstance(value, Path):
                result[key] = str(value)
            else:
                result[key] = value

        return result

    def __or__(self, that):
        """
        Implements a recursive dictionary-style union: self | that

        For each key in either dictionary (or Dynamic instance), if both values are dicts (or Dynamic),
        merge them recursively. Otherwise, the value from the right-hand side (that) takes precedence.
        The merge is non-mutative: a new Dynamic instance is returned.

        Supports 'that' being a dict or Dynamic instance.

        Example:
            Dynamic({'x': 1, 'y': {'z': 2}}) | {'y': {'w': 3}}
            =>
            Dynamic({'x': 1, 'y': {'z': 2, 'w': 3}})
        """

        def to_dict_like(val):
            if isinstance(val, Dynamic):
                return val.to_dict()

            return val

        def recursive_union(left, right):
            left = to_dict_like(left)
            right = to_dict_like(right)

            if isinstance(left, dict) and isinstance(right, dict):
                out = dict(left)

                for k, v in right.items():
                    if k in out:
                        out[k] = recursive_union(out[k], v)
                    else:
                        out[k] = v

                return out

            return right

        merged = recursive_union(self, that)
        return Dynamic(merged)

    def __ror__(self, that):
        """
        Support dictionary-style union where Dynamic is the right operand (e.g., dict | Dynamic):

        Ensures left | right semantics, so the right-hand side (self) values take precedence.
        Wraps the left operand as a Dynamic (if needed), and merges using __or__.

        Example:
            {'x': 1, 'y': {'z': 2}} | Dynamic({'y': {'w': 3}})
            =>
            Dynamic({'x': 1, 'y': {'z': 2, 'w': 3}})
        """
        return Dynamic(that) | self

def get_annotation_constructors(obj_or_class, attr_name) -> tuple[type]:
    """
    Given an object or class and an attribute name, read the annotation for that
    attribute and return a tuple of constructor types.

    Return value:
      - A tuple of types/classes (e.g. (dict,), (list,), (str, int))

    Parameters:
      - obj_or_class: instance or class where attr_name is annotated.
      - attr_name: name of the attribute whose annotation to inspect.

    Notes:
      - Uses typing.get_type_hints to resolve forward references where possible.
      - If the attribute is not annotated (or not present in resolved hints),
        returns an empty tuple.
    """
    # Determine class to inspect
    cls = obj_or_class if inspect.isclass(obj_or_class) else obj_or_class.__class__

    # Resolve annotations, so ForwardRef and string annotations are resolved where possible
    hints = get_type_hints(cls)

    if attr_name not in hints:
        return tuple()

    tp = hints[attr_name]

    # include types.UnionType for PEP 604 (X | Y) if available
    union_origin_candidates = {typing.Union}
    if hasattr(types, "UnionType"):
        union_origin_candidates.add(types.UnionType)

    def resolve(t):
        # Normalize typing.Any -> object
        if t is Any:
            print("one")
            return (object,)

        origin = get_origin(t)
        args = get_args(t)

        # Non-parameterized types (including builtin types)
        if origin is None:
            # If it's a plain type, return it as a singleton tuple
            if isinstance(t, type):
                print("two")
                return (t,)
            # If it's still a typing construct (rare after get_type_hints), try common cases:
            # e.g. typing.Dict without args -> treat as dict
            name = getattr(t, "__qualname__", None) or getattr(t, "__name__", None) or ""
            mapping = {"dict": dict, "list": list, "tuple": tuple, "set": set}
            if name.lower() in mapping:
                print("three")
                return (mapping[name.lower()],)
            # fallback: return the object itself in a tuple
            print("four")
            return (t,)

        # Handle Union (including Optional) for typing.Union and PEP604 unions
        if origin in union_origin_candidates or getattr(origin, "__name__", "") == "Union":
            members = []
            for a in args:
                ra = resolve(a)
                # ra should be a tuple; extend members with its items
                if isinstance(ra, tuple):
                    members.extend(ra)
                else:
                    members.append(ra)
            print("five")
            return tuple(members)

        # For parameterized generic classes (e.g. collections.abc.Mapping)
        # prefer the origin if it is a type
        if isinstance(origin, type):
            print(f"six", origin, args)

            # probably a list/tuple/set
            if len(args) == 1:
                return ((lambda i: origin(args[0](ii) for ii in i)),)

            return (origin,)

        # fallback: return origin as a single-item tuple
        print("six")
        return (origin,)

    resolved = resolve(tp)
    print(f"{attr_name} resolved -> {resolved}")
    return resolved
