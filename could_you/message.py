from typing import List, Dict, Optional, Literal, Any
import json
import sys


class _Dynamic:

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
            if isinstance(value, dict):
                # If the value is a dictionary, convert it into another _Dynamic instance
                value = _Dynamic(value)

            elif hasattr(value, "__dict__"):
                # If the value is a dictionary, convert it into another _Dynamic instance
                value = _Dynamic(vars(value))

            elif isinstance(value, list):
                # If the value is a list, check for non-scalar values and convert them
                value = [
                    _Dynamic(item) if isinstance(item, dict) or hasattr(item, "__dict__") else item
                    for item in value
                ]

            setattr(self, key, value)

    def __getattr__(self, attr: str) -> Any:
        # Convert snake_case to camelCase
        camel_case_attr = "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(attr.split("_"))
        )
        # Check if the camelCase attribute exists
        if camel_case_attr in self.__dict__:
            return self.__dict__[camel_case_attr]

        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Recursively converts the _Dynamic object and its nested _Dynamic instances
        back into a raw dictionary.
        """
        result = {}

        for key, value in self.__dict__.items():
            # If the value is another _Dynamic instance, call to_dict on it
            if isinstance(value, _Dynamic):
                result[key] = value.to_dict()
            # If the value is a list, process each item
            elif isinstance(value, list):
                result[key] = [
                    item.to_dict() if isinstance(item, _Dynamic) else item for item in value
                ]
            else:
                result[key] = value

        return result



class ToolUse(_Dynamic):
    tool_use_id: str
    name: str
    input: Any


class ToolResultContent(_Dynamic):
    text: str
    json: Any


class ToolResult(_Dynamic):
    tool_use_id: str
    content: List[ToolResultContent]
    status: Literal["success", "error"]


class Content(_Dynamic):
    type: Literal["text"]
    text: Optional[str]
    # image: Optional[Image]
    # document: Optional[Document]
    # video: Optional[Video]
    tool_use: Optional[ToolUse]
    tool_result: Optional[ToolResult]
    # guard_content: Optional[GuardContent]
    # cache_point: Optional[CachePoint]
    # reasoning_content: Optional[ReasoningContent]


class Message(_Dynamic):
    role: Literal["user", "assistant"]
    content: List[Content]

    def print(self, file=None, verbose=False):
        output = file if file is not None else sys.stdout

        print(f"*** {self.role} ***", file=output)
        for content in self.content:
            for key, val in vars(content).items():
                if key == 'text':
                    # Always print text content
                    print(f"    {key}:", file=output)
                    for line in val.splitlines():
                        print(f"        {line}", file=output)
                elif verbose:
                    # Print full details in verbose mode
                    print(f"    {key}:", file=output)
                    if isinstance(val, str):
                        for line in val.splitlines():
                            print(f"        {line}", file=output)
                    elif isinstance(val, _Dynamic):
                        # Pretty print JSON with consistent indentation
                        v = val.to_dict() if isinstance(val, _Dynamic) else val
                        json_lines = json.dumps(v, indent=2).splitlines()
                        for line in json_lines:
                            print(f"        {line}", file=output)
                    else:
                        # For other types, convert to string
                        print(f"        {str(val)}", file=output)
                else:
                    # In non-verbose mode, print simplified content
                    if key == 'toolUse' and isinstance(val, _Dynamic):
                        print(f"    {key}: {val.name}", file=output)
                    elif isinstance(val, _Dynamic):
                        print(f"    <{key}>", file=output)
        print(file=output)