from typing import Optional, List, Dict, Tuple
from contextlib import AsyncExitStack
from mcp import ClientSession, Tool
from .mcp_server import MCPServer
from .config import Config
import boto3


class MCPHost:
    def __init__(self, *, config: Config):
        # Initialize session and client objects
        self.servers: List[MCPServer] = config.servers
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.config = config
        self.tools: Dict[str, Tuple[MCPServer, Tool]] = {}

    async def __aenter__(self):
        # TODO: should this use create_task or TaskGroup?
        for s in self.servers:
            await s.connect(exit_stack=self.exit_stack)

        for s in self.servers:
            for t in s.tools:
                older_server, old_tool = self.tools.get(t.name, (None, None))
                if older_server and old_tool:
                    print(
                        f"warning: duplicate {t.name} tool found. using {s.name} version instead of {old_server.name}"
                    )
                self.tools[t.name] = (s, t)

        return self

    async def __aexit__(self, *args):
        """Clean up resources"""
        await self.exit_stack.aclose()

    async def process_query_aws(self, query: str):
        bedrock = boto3.client("bedrock-runtime")
        # Prepare the request for Nova Pro model
        system = [{"text": self.config.prompt}]

        messages = [{"role": "user", "content": [{"text": query}]}]
        ran_tool = False

        while True:
            # Call Bedrock with Nova Pro model
            response = bedrock.converse(
                modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
                messages=messages,
                system=system,
                inferenceConfig={"maxTokens": 300, "topP": 0.1, "temperature": 0.3},
                toolConfig=convert_tools_for_bedrock([t[1] for t in self.tools.values()]),
            )

            output_message = response["output"]["message"]
            messages.append(output_message)
            role = output_message["role"]

            # Print the model's response
            for content in output_message["content"]:
                text = content.get("text", None)
                tool_use = content.get("toolUse", None)

                if text:
                    print(f">>> *** {role} *** ===")
                    print(text)
                    print(f"<<< *** {role} *** ===")

                elif tool_use:
                    ran_tool = True
                    tool_name = tool_use["name"]
                    tool_input = tool_use["input"]
                    server = self.tools[tool_name][0]
                    print(f">>> *** tool:{server.name}.{tool_name} *** ===")

                    tool_result = {"toolUseId": tool_use["toolUseId"], "content": []}

                    try:
                        tool_response = await server.call_tool(tool_name, tool_input)

                        # Convert tool response to expected format
                        tool_result["content"].append({"text": tool_response.content[0].text})
                    except Exception as err:
                        tool_result["content"].append({"text": f"Error: {str(err)}"})
                        tool_result["status"] = "error"

                    print(tool_result["content"][0]["text"])
                    print(f"<<< *** tool:{server.name}.{tool_name} *** ===")

                    # Add tool result to messages
                    messages.append({"role": "user", "content": [{"toolResult": tool_result}]})

            if not ran_tool:
                print(f"stopping as there is nothing to do")
                break

    async def chat_loop(self, query: str):
        """Run an interactive chat loop"""
        try:
            await self.process_query_aws(query)

        except Exception as e:
            print(f"\nError: {str(e)}")


def convert_tools_for_bedrock(tools: List[Tool]):
    converted_tools = []

    for tool in tools:
        converted_tool = {
            "toolSpec": {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {"json": tool.inputSchema},
            }
        }
        converted_tools.append(converted_tool)

    return {"tools": converted_tools}
