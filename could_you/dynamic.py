import json
from pathlib import Path
from typing import Any, Literal

import yaml

from .logging_config import LOGGER


class Dynamic:
    def __init__(self, input_dict: Any = None, **kwargs: Any) -> None:
        # Merge input_dict and kwargs, with kwargs taking precedence
        input_dict = input_dict or {}

        # If input_data is not a dictionary but has a __dict__, unpack it
        if hasattr(input_dict, "__dict__"):
            # assuming no __slots__
            input_dict = vars(input_dict)

        combined_data = {**input_dict, **kwargs}

        # Use setattr to set attributes from the dictionary
        for key, value in combined_data.items():
            new_value = value

            if isinstance(value, dict):
                # If the value is a dictionary, convert it into another Dynamic instance
                new_value = Dynamic(value)

            elif hasattr(value, "__dict__"):
                # If the value is a dictionary, convert it into another Dynamic instance
                new_value = Dynamic(vars(value))

            elif isinstance(value, list | set | tuple):
                # If the value is a list, check for non-scalar values and convert them
                new_value = [
                    Dynamic(item) if isinstance(item, dict) or hasattr(item, "__dict__") else item for item in value
                ]

            setattr(self, key, new_value)

    def __getattr__(self, attr: str) -> Any:
        # Convert snake_case to camelCase
        camel_case_attr = "".join(word.capitalize() if i > 0 else word for i, word in enumerate(attr.split("_")))
        # Check if the camelCase attribute exists
        if camel_case_attr in self.__dict__:
            return self.__dict__[camel_case_attr]

        return None

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
