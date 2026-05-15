from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OllamaConfig:
    model: str = "qwen3-coder"#"deepseek-coder:6.7b"
    host: str = "http://localhost:11434"
    temperature: float = 0.1
    num_ctx: int = 8192


def clean_schema(schema: Any) -> Any:
    """
    Strip FastMCP/Pydantic JSON schema down to the subset that Ollama accepts reliably.
    """

    if isinstance(schema, list):
        return [clean_schema(item) for item in schema]

    if not isinstance(schema, dict):
        return schema

    allowed_keys = {
        "type",
        "description",
        "properties",
        "required",
        "items",
        "enum",
    }

    cleaned: dict[str, Any] = {}

    for key, value in schema.items():
        if key not in allowed_keys:
            continue

        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {
                prop_name: clean_schema(prop_schema)
                for prop_name, prop_schema in value.items()
                if isinstance(prop_schema, dict)
            }
        else:
            cleaned[key] = clean_schema(value)

    return cleaned


def ensure_object_schema(parameters: Any) -> dict[str, Any]:
    """
    Ollama function parameters should be a JSON object schema.
    """

    if not isinstance(parameters, dict):
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    parameters = clean_schema(parameters)

    if parameters.get("type") != "object":
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    if "properties" not in parameters or not isinstance(parameters["properties"], dict):
        parameters["properties"] = {}

    if "required" not in parameters or not isinstance(parameters["required"], list):
        parameters["required"] = []

    return parameters


def to_ollama_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """
    Convert MCP/FastMCP-style tool schema to Ollama/OpenAI-style function tool schema.
    """

    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        function = tool["function"]

        name = function.get("name")
        if not name:
            raise ValueError(f"Ollama tool function is missing name: {tool}")

        parameters = ensure_object_schema(function.get("parameters", {}))

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": function.get("description", ""),
                "parameters": parameters,
            },
        }

    name = tool.get("name")
    if not name:
        raise ValueError(f"Tool is missing name: {tool}")

    parameters = (
        tool.get("parameters")
        or tool.get("inputSchema")
        or tool.get("input_schema")
        or {}
    )

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": ensure_object_schema(parameters),
        },
    }


def to_ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [to_ollama_tool(tool) for tool in tools]


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config

    def chat_raw(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.host.rstrip('/')}/api/chat"

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_ctx": self.config.num_ctx,
            },
        }

        if tools:
            payload["tools"] = to_ollama_tools(tools)

        data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama HTTP {exc.code} {exc.reason}\n"
                f"URL: {url}\n"
                f"Response body:\n{error_body}\n\n"
                f"Payload sent:\n{json.dumps(payload, indent=2)}"
            ) from exc

        except Exception as exc:
            raise RuntimeError(
                "Could not call Ollama. Check that Ollama is running and the model is pulled. "
                f"Original error: {exc}"
            ) from exc

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        body = self.chat_raw(messages, tools=tools)
        return body.get("message", {}).get("content", "")

    def generate(self, prompt: str, system: str | None = None) -> str:
        messages: list[dict[str, Any]] = []

        if system:
            messages.append(
                {
                    "role": "system",
                    "content": system,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        return self.chat(messages)