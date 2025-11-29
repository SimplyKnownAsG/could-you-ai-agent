import json
from pathlib import Path
from typing import Any

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

            elif isinstance(value, list):
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

    def dumps(self, path: Path):
        if path.suffix == ".json":
            loader = json.load
        elif path.suffix in {".yaml", ".yml"}:
            loader = yaml.safe_load
        else:
            LOGGER.warning(f"Unrecognized file extension {path.suffix} in {path}, trying YAML")
            loader = yaml.safe_load

        with open(path) as file:
            return Dynamic(loader(file))

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
            elif isinstance(value, list | set):
                result[key] = [item.to_dict() if isinstance(item, Dynamic) else item for item in value]
            elif isinstance(value, Path):
                result[key] = str(value)
            else:
                result[key] = value

        return result
