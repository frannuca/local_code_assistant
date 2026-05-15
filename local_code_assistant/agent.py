from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .ollama_client import OllamaClient
from .prompts import PATCH_PROMPT, SYSTEM_PROMPT
from .repo import auto_select_files, git_diff as repo_git_diff, read_files, scan_repo


ToolFunc = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class LocalTool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: ToolFunc

    def as_ollama_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class CodeAgent:
    """
    Ollama tool-calling agent for local repository edits.

    This class intentionally does more than prompt the model:
    - It preselects and reads relevant files in code before asking the model to edit.
    - It executes model-requested tools.
    - If the model only explains and never edits, it falls back to a patch-only request,
      then applies that patch with git apply.
    - It can keep conversation context across turns for interactive CLI sessions.
    """

    EDIT_KEYWORDS = {
        "improve",
        "fix",
        "refactor",
        "optimize",
        "optimise",
        "parallel",
        "parallelism",
        "parallelize",
        "parallelise",
        "implement",
        "change",
        "modify",
        "update",
        "rewrite",
        "add",
        "remove",
    }

    def __init__(
        self,
        client: OllamaClient,
        repo: Path,
        max_steps: int = 12,
        auto_files: int = 20,
        force_edit: bool = True,
    ):
        self.client = client
        self.repo = repo.resolve()
        self.max_steps = max_steps
        self.auto_files = auto_files
        self.force_edit = force_edit
        self.tools = self._build_tools()
        self.messages: list[dict[str, Any]] = []
        self.reset_context()

    def reset_context(self) -> None:
        self.messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n\nYou are a repository-editing agent, not a chat assistant.\n"
                    "You have local tools that inspect and modify files.\n"
                    "For implementation/refactor/optimization requests you must produce real file changes.\n"
                    "Mandatory workflow: inspect files, read files, apply_patch or write_file, then git_diff.\n"
                    "Prefer apply_patch for existing files. Use write_file only for new files or complete replacement.\n"
                    "Do not stop after advice when the user asks to change code."
                ),
            }
        ]

    def run(self, question: str, *, keep_context: bool = False) -> str:
        if not keep_context:
            self.reset_context()

        wants_edit = self._looks_like_edit_request(question)

        self.messages.append(
            {
                "role": "user",
                "content": f"Repository root: {self.repo}\n\nTask:\n{question}",
            }
        )

        # Code-level enforcement: do the first inspection steps ourselves. This prevents
        # the model from spending all iterations deciding whether it should inspect.
        selected_files = self._preload_relevant_context(question)

        made_change = False
        used_tool = True  # preload already used repository context
        last_content = ""

        for _ in range(self.max_steps):
            response = self.client.chat_raw(
                messages=self.messages,
                tools=[tool.as_ollama_tool() for tool in self.tools.values()],
            )

            message = response.get("message", {})
            self.messages.append(message)
            last_content = message.get("content", "") or ""
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                if wants_edit and not made_change:
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You have not modified files yet. Now create a unified diff and call apply_patch. "
                                "Do not explain. After apply_patch, call git_diff."
                            ),
                        }
                    )
                    # Try one or more tool-calling turns, then fall back to direct patch generation.
                    if self._too_many_no_edit_turns():
                        break
                    continue

                return last_content

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name")
                args = self._parse_tool_args(fn.get("arguments") or {})

                result = self.call_tool(name, args)
                used_tool = True

                if name in {"write_file", "apply_patch"} and self._tool_result_indicates_change(result):
                    made_change = True

                # Ollama accepts role=tool messages. Include both name and content;
                # do not use only a custom key like tool_name.
                self.messages.append(
                    {
                        "role": "tool",
                        "name": name or "unknown_tool",
                        "content": result,
                    }
                )

                if made_change:
                    diff = self.call_tool("git_diff", {})
                    self.messages.append(
                        {
                            "role": "tool",
                            "name": "git_diff",
                            "content": diff,
                        }
                    )
                    return self._summarize_after_change(question, diff)

        if wants_edit and self.force_edit and not made_change:
            return self._force_patch(question, selected_files)

        suffix = "" if used_tool else " No tools were used."
        return f"Stopped: maximum tool-calling steps reached.{suffix}\n\nLast model content:\n{last_content}"

    def call_tool(self, name: str | None, args: dict[str, Any]) -> str:
        if not name or name not in self.tools:
            return f"Unknown tool: {name}"
        try:
            return self.tools[name].func(args)
        except Exception as exc:
            return f"Tool {name} failed: {type(exc).__name__}: {exc}"

    def _looks_like_edit_request(self, question: str) -> bool:
        q = question.lower()
        return any(word in q for word in self.EDIT_KEYWORDS)

    def _too_many_no_edit_turns(self) -> bool:
        reminders = [
            m
            for m in self.messages
            if m.get("role") == "user" and "You have not modified files yet" in m.get("content", "")
        ]
        return len(reminders) >= 2

    def _parse_tool_args(self, args: Any) -> dict[str, Any]:
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                return {"_raw": args}
        return {"value": args}

    def _tool_result_indicates_change(self, result: str) -> bool:
        lower = result.lower()
        failures = [
            "failed",
            "error",
            "blocked",
            "not found",
            "cannot",
            "check passed",
            "would apply",
        ]
        return not any(token in lower for token in failures)

    def _preload_relevant_context(self, question: str) -> list[str]:
        selected = auto_select_files(self.repo, question, max_files=self.auto_files)
        if not selected:
            selected = [f.rel_path for f in scan_repo(self.repo, max_files=self.auto_files)]

        context = read_files(self.repo, selected, max_chars_per_file=30_000)
        self.messages.append(
            {
                "role": "tool",
                "name": "auto_find_relevant_files",
                "content": "\n".join(selected) if selected else "No relevant files found",
            }
        )
        self.messages.append(
            {
                "role": "tool",
                "name": "read_multiple_files",
                "content": context,
            }
        )
        self.messages.append(
            {
                "role": "user",
                "content": (
                    "Relevant files have already been selected and read above. "
                    "If this is an edit task, create a unified diff and call apply_patch now."
                ),
            }
        )
        return selected

    def _force_patch(self, question: str, selected_files: list[str]) -> str:
        """
        Last resort: ask for a patch-only answer and apply it ourselves.
        This is the code-level enforcement path when tool calling keeps producing advice.
        """
        if not selected_files:
            selected_files = [f.rel_path for f in scan_repo(self.repo, max_files=self.auto_files)]

        context = read_files(self.repo, selected_files, max_chars_per_file=40_000)
        prompt = f"""
Repository: {self.repo}
Selected files:
{chr(10).join('- ' + f for f in selected_files)}

Task:
{question}

Code context:
{context}

Return ONLY a valid unified diff patch that modifies the repository.
Do not include markdown fences or prose.
""".strip()

        patch = self.client.generate(
            prompt,
            system=(
                SYSTEM_PROMPT
                + "\n\n"
                + PATCH_PROMPT
                + "\n\nYou must return a real patch for the requested code change."
            ),
        ).strip()

        if not self._looks_like_unified_diff(patch):
            patch_path = self.repo / ".local_code_assistant_last_response.txt"
            patch_path.write_text(patch, encoding="utf-8")
            return (
                "The model still did not produce a valid unified diff. "
                f"I saved its last response to {patch_path}.\n\n"
                f"Response:\n{patch}"
            )

        result = self.call_tool("apply_patch", {"patch_content": patch})
        if not self._tool_result_indicates_change(result):
            patch_path = self.repo / ".local_code_assistant_failed.patch"
            patch_path.write_text(patch, encoding="utf-8")
            return (
                "Generated a patch, but applying it failed. "
                f"Saved patch to {patch_path}.\n\n"
                f"Apply result:\n{result}\n\nPatch:\n{patch}"
            )

        diff = self.call_tool("git_diff", {})
        return self._summarize_after_change(question, diff)

    def _looks_like_unified_diff(self, text: str) -> bool:
        return "diff --git " in text or ("--- " in text and "+++ " in text and "@@" in text)

    def _summarize_after_change(self, question: str, diff: str) -> str:
        if not diff.strip() or diff.strip() == "(no diff)":
            return "A modification tool reported success, but git diff is empty. Check whether the target repo is a git repository."

        summary_prompt = f"""
Task:
{question}

Git diff produced by the agent:
{diff}

Summarize the actual file changes concisely. Mention that files were modified.
""".strip()
        return self.client.generate(summary_prompt, system=SYSTEM_PROMPT)

    def _safe_path(self, path: str) -> Path:
        candidate = (self.repo / path).resolve()
        if not str(candidate).startswith(str(self.repo)):
            raise ValueError(f"Path escapes repository: {path}")
        return candidate

    def _build_tools(self) -> dict[str, LocalTool]:
        def list_files(args: dict[str, Any]) -> str:
            max_files = int(args.get("max_files", 300))
            files = scan_repo(self.repo, max_files=max_files)
            return "\n".join(f"{f.rel_path}\t{f.size} bytes" for f in files)

        def read_file(args: dict[str, Any]) -> str:
            path = str(args["path"])
            offset = int(args.get("offset", 1))
            limit = args.get("limit")
            limit = int(limit) if limit is not None else None
            p = self._safe_path(path)
            if not p.exists():
                return f"File not found: {path}"
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            start = max(offset - 1, 0)
            end = len(lines) if limit is None else min(start + limit, len(lines))
            return "\n".join(f"{i+1:5d} | {line}" for i, line in enumerate(lines[start:end], start=start))

        def read_multiple(args: dict[str, Any]) -> str:
            files = [str(f) for f in args.get("files", [])]
            max_chars = int(args.get("max_chars_per_file", 30000))
            return read_files(self.repo, files, max_chars_per_file=max_chars)

        def auto_find(args: dict[str, Any]) -> str:
            question = str(args["question"])
            max_files = int(args.get("max_files", 20))
            selected = auto_select_files(self.repo, question, max_files=max_files)
            return "\n".join(selected) if selected else "No relevant files found"

        def write_file(args: dict[str, Any]) -> str:
            p = self._safe_path(str(args["path"]))
            content = str(args["content"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Wrote {p.relative_to(self.repo)} ({len(content)} bytes)"

        def apply_patch(args: dict[str, Any]) -> str:
            patch_content = str(args["patch_content"])
            dry_run = bool(args.get("dry_run", False))
            cmd = ["git", "apply"]
            if dry_run:
                cmd.append("--check")
            cmd.append("-")
            result = subprocess.run(
                cmd,
                cwd=self.repo,
                input=patch_content,
                text=True,
                capture_output=True,
                timeout=60,
            )
            if result.returncode == 0:
                return "Patch check passed" if dry_run else "Patch applied"
            return result.stderr or result.stdout or "Patch failed"

        def git_diff(args: dict[str, Any]) -> str:
            return repo_git_diff(self.repo) or "(no diff)"

        def git_status(args: dict[str, Any]) -> str:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.repo,
                text=True,
                capture_output=True,
                timeout=30,
            )
            return result.stdout or result.stderr or "(clean)"

        def run_command(args: dict[str, Any]) -> str:
            command = [str(x) for x in args.get("command", [])]
            allowed = {
                ("dotnet", "build"),
                ("dotnet", "test"),
                ("git", "diff"),
                ("git", "status"),
                ("python", "-m"),
                ("pytest",),
            }
            if not command:
                return "No command provided"
            key = tuple(command[:2]) if len(command) >= 2 else tuple(command[:1])
            if key not in allowed:
                return f"Blocked command: {' '.join(command)}"
            result = subprocess.run(
                command,
                cwd=self.repo,
                text=True,
                capture_output=True,
                timeout=180,
            )
            return (result.stdout + "\n" + result.stderr).strip() or "(no output)"

        schema_string = {"type": "string"}
        schema_integer = {"type": "integer"}
        schema_boolean = {"type": "boolean"}

        tools = [
            LocalTool(
                "list_files",
                "List text/code files in the repository.",
                {"type": "object", "properties": {"max_files": schema_integer}, "required": []},
                list_files,
            ),
            LocalTool(
                "read_file",
                "Read a repository file with optional 1-based line offset and limit.",
                {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": schema_string, "offset": schema_integer, "limit": schema_integer},
                },
                read_file,
            ),
            LocalTool(
                "read_multiple_files",
                "Read multiple repository files.",
                {
                    "type": "object",
                    "required": ["files"],
                    "properties": {
                        "files": {"type": "array", "items": schema_string},
                        "max_chars_per_file": schema_integer,
                    },
                },
                read_multiple,
            ),
            LocalTool(
                "auto_find_relevant_files",
                "Find files that look relevant to a question.",
                {
                    "type": "object",
                    "required": ["question"],
                    "properties": {"question": schema_string, "max_files": schema_integer},
                },
                auto_find,
            ),
            LocalTool(
                "write_file",
                "Create or completely replace a repository file. Use for new files or deliberate full-file replacement.",
                {
                    "type": "object",
                    "required": ["path", "content"],
                    "properties": {"path": schema_string, "content": schema_string},
                },
                write_file,
            ),
            LocalTool(
                "apply_patch",
                "Apply a unified diff patch to modify existing repository files. Use this for code edits, fixes, refactors, optimizations, and parallelization changes.",
                {
                    "type": "object",
                    "required": ["patch_content"],
                    "properties": {"patch_content": schema_string, "dry_run": schema_boolean},
                },
                apply_patch,
            ),
            LocalTool("git_diff", "Show current git diff.", {"type": "object", "properties": {}, "required": []}, git_diff),
            LocalTool("git_status", "Show current git status.", {"type": "object", "properties": {}, "required": []}, git_status),
            LocalTool(
                "run_command",
                "Run a whitelisted command: dotnet build/test, git diff/status, pytest, or python -m pytest.",
                {
                    "type": "object",
                    "required": ["command"],
                    "properties": {"command": {"type": "array", "items": schema_string}},
                },
                run_command,
            ),
        ]
        return {tool.name: tool for tool in tools}
