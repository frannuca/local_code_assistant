from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from rich import print as rprint
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.console import Console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    def rprint(*args, **kwargs):
        print(*args)
    class Panel:
        def __init__(self, *args, **kwargs):
            pass
    Console = type('Console', (), {})

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
        max_steps: int = 50,
        auto_files: int = 20,
        force_edit: bool = True,
        max_context_messages: int = 20,
        verbose: bool = False,
        confirm_edits: bool = False,
        auto_test: bool = False,
    ):
        self.client = client
        self.repo = repo.resolve()
        self.max_steps = max_steps
        self.auto_files = auto_files
        self.force_edit = force_edit
        self.max_context_messages = max_context_messages
        self.verbose = verbose
        self.confirm_edits = confirm_edits
        self.auto_test = auto_test
        # Per-session content cache. Key: resolved absolute path string.
        # Value: (mtime_ns, text). Invalidated on every mutating tool call.
        self._read_cache: dict[str, tuple[int, str]] = {}
        self.tools = self._build_tools()
        self.messages: list[dict[str, Any]] = []
        self.reset_context()

    def _cached_read(self, p: Path) -> str:
        key = str(p)
        try:
            mtime = p.stat().st_mtime_ns
        except OSError:
            self._read_cache.pop(key, None)
            raise
        cached = self._read_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        text = p.read_text(encoding="utf-8", errors="replace")
        self._read_cache[key] = (mtime, text)
        return text

    def _invalidate_cache(self, p: Path) -> None:
        self._read_cache.pop(str(p), None)

    def _show_preview(self, title: str, before: str, after: str, label: str) -> None:
        """Render a unified diff preview for a proposed change."""
        diff_lines = list(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"{label} (current)",
                tofile=f"{label} (proposed)",
                n=3,
            )
        )
        diff_text = "".join(diff_lines) or "(no textual diff)"
        if HAS_RICH:
            rprint(Panel(Syntax(diff_text, "diff", theme="monokai", line_numbers=False), title=title))
        else:
            print(f"=== {title} ===")
            print(diff_text)

    def _run_auto_test(self) -> str | None:
        """Detect repo type and run a short test/build. Returns formatted output or None."""
        if not self.auto_test:
            return None
        cmd: list[str] | None = None
        label = ""
        if (self.repo / "pyproject.toml").exists() or any(self.repo.glob("test_*.py")) or (self.repo / "tests").is_dir():
            cmd = ["pytest", "--tb=short", "-q", "-x"]
            label = "pytest"
        elif any(self.repo.glob("*.csproj")) or any(self.repo.glob("*.sln")):
            cmd = ["dotnet", "build", "--nologo", "-v", "quiet"]
            label = "dotnet build"
        elif (self.repo / "package.json").exists():
            cmd = ["npm", "test", "--silent"]
            label = "npm test"
        if cmd is None:
            return None
        self._log(f"[bold]🧪 Auto-test: {label}[/bold]")
        try:
            result = subprocess.run(
                cmd, cwd=self.repo, capture_output=True, text=True, timeout=180
            )
        except FileNotFoundError:
            return f"[{label}] command not available"
        except subprocess.TimeoutExpired:
            return f"[{label}] timed out after 180s"
        out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        status = "PASS" if result.returncode == 0 else f"FAIL (exit {result.returncode})"
        # Trim output to keep context lean.
        if len(out) > 4000:
            out = out[:2000] + "\n... [truncated] ...\n" + out[-1500:]
        return f"[{label}] {status}\n{out}"

    def _prompt_accept(self) -> bool:
        """Prompt the user y/N. Default to reject; reject outright if not a TTY."""
        if not sys.stdin.isatty():
            self._log("[yellow]⚠️  confirm_edits is on but stdin is not a TTY — rejecting change[/yellow]")
            return False
        try:
            answer = input("Apply this change? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ("y", "yes")

    def reset_context(self) -> None:
        self._read_cache.clear()
        self.messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n\nYou are a repository-editing agent, not a chat assistant.\n"
                    "You have local tools that inspect and modify files.\n"
                    "For implementation/refactor/optimization requests you must produce real file changes.\n"
                    "Mandatory workflow: use search_text to locate code, read_file the target, "
                    "then call edit_file with exact search/replace strings, then git_diff.\n"
                    "Prefer edit_file for existing files. Use write_file only for new files or complete replacement.\n"
                    "apply_patch (unified diff) is a last-resort tool — avoid it when edit_file would work.\n"
                    "Do not stop after advice when the user asks to change code."
                ),
            }
        ]

    def _build_message(self, role: str, content: str) -> dict[str, Any]:
        return {"role": role, "content": content}
    def _trim_context(self) -> None:
        """
        Keep message history bounded in interactive mode.
        Always keep: system message + last N messages.
        """
        if len(self.messages) <= self.max_context_messages:
            return
        # Keep system message (index 0) + last (max_context_messages - 1) messages
        system = self.messages[0:1]
        recent = self.messages[-(self.max_context_messages - 1) :]
        oldMessages = self.messages[-(self.max_context_messages - 1) :]
        #summarize the old ones:
        summary = self.client.chat(
                [{
                    "role": "user",
                    "content": (
                        f"You are in an interactive session with a human performing code changes and reviews. "
                        f"Previous conversation history is being summarized to save space, but the system message and recent messages are preserved in full. "
                        f"Summarize the following conversation history in a maximum of 1024 words, focusing on the main previous changes and any important details. Be concise and informative.\n\n"
                        f"{json.dumps(oldMessages)}"
                    ),
                }
            ]
        )
        self._log(f"[dim]🗂️  Context trimmed. Summary of previous conversation:\n{summary}[/dim]")
        self.messages = system+[self._build_message("user",summary)] + recent

    def _log(self, message: str, style: str = "") -> None:
        """Print verbose feedback to console if enabled."""
        if self.verbose:
            rprint(message)

    def _log_thinking(self, title: str, content: str, max_lines: int = 5) -> None:
        """Display model thinking with formatted output."""
        if not self.verbose:
            return
        lines = content.split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines)"]
        content_short = "\n".join(lines)
        rprint(f"[dim]💭 {title}:[/dim]", content_short[:200])

    def _log_tool_call(self, tool_name: str, args: dict) -> None:
        """Display tool call information."""
        if not self.verbose:
            return
        
        # For apply_patch, show more content to debug truncation issues
        if tool_name == "apply_patch" and "patch_content" in args:
            patch = str(args.get("patch_content", ""))
            if len(patch) > 2000:
                patch_display = patch[:1500] + f"\n... [{len(patch) - 1500} more chars]"
            else:
                patch_display = patch
            
            rprint(f"[cyan]🔧 Calling tool:[/cyan] [bold]{tool_name}[/bold]")
            rprint(f"[dim]   Patch size: {len(patch)} chars[/dim]")
            rprint(f"[dim yellow]⚠️  Showing first 1500 chars:[/dim yellow]")
            rprint(f"[dim]{patch_display}[/dim]")
        else:
            # For other tools, use regular truncation
            args_str = json.dumps(args, indent=2)[:500]
            rprint(f"[cyan]🔧 Calling tool:[/cyan] [bold]{tool_name}[/bold]")
            if args_str:
                rprint(f"[dim]   Args: {args_str}[/dim]")

    def _log_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """Display tool result."""
        if not self.verbose:
            return
        status = "✓" if success else "✗"
        color = "green" if success else "red"
        
        # For patches, show more detail on error
        if tool_name == "apply_patch" and not success:
            rprint(f"[{color}]{status} Patch result:[/] [bold red]FAILED[/bold red]")
            rprint(f"[red]Error details:[/red]")
            rprint(f"[red]{result}[/red]")
            rprint(f"[yellow]⚠️  Possible causes:[/yellow]")
            rprint(f"[dim]  1. Patch content is incomplete or truncated[/dim]")
            rprint(f"[dim]  2. File paths in patch don't exist[/dim]")
            rprint(f"[dim]  3. File content doesn't match patch expectations[/dim]")
            rprint(f"[dim]  4. Patch format is invalid (missing headers, etc)[/dim]")
        else:
            result_short = result[:200]
            rprint(f"[{color}]{status} Tool result:[/] {result_short}")

    def _log_step(self, step_num: int, total_steps: int) -> None:
        """Display current step."""
        if not self.verbose:
            return
        rprint(f"[blue]⏳ Step {step_num}/{total_steps}[/blue]")

    def _log_file_selected(self, files: list[str]) -> None:
        """Display selected files."""
        if not self.verbose:
            return
        rprint(f"[yellow]📁 Found {len(files)} relevant files:[/yellow]")
        for f in files[:5]:
            rprint(f"[dim]   • {f}[/dim]")
        if len(files) > 5:
            rprint(f"[dim]   ... and {len(files) - 5} more[/dim]")

    def run(self, question: str, *, keep_context: bool = False) -> str:
        if not keep_context:
            self.reset_context()
        else:
            self._log("[bold cyan]📝 Continuing interactive session...[/bold cyan]")

        wants_edit = self._looks_like_edit_request(question)
        
        if wants_edit:
            self._log("[bold green]✏️  Edit request detected[/bold green]")

        # Trim context before adding new message in interactive mode
        if keep_context:
            self._trim_context()

        self._log(f"[bold]📋 Task:[/bold] {question[:100]}")

        self.messages.append(
            {
                "role": "user",
                "content": f"Repository root: {self.repo}\n\nTask:\n{question}",
            }
        )

        # Code-level enforcement: do the first inspection steps ourselves. This prevents
        # the model from spending all iterations deciding whether it should inspect.
        self._log("[yellow]🔍 Preloading relevant context...[/yellow]")
        selected_files = self._preload_relevant_context(question, skip_large_contents=keep_context)
        self._log_file_selected(selected_files)

        made_change = False
        used_tool = True  # preload already used repository context
        last_content = ""

        for step_idx in range(self.max_steps):
            self._log_step(step_idx + 1, self.max_steps)
            self._log("[bold]🤔 Waiting for model response...[/bold]")
            
            response = self.client.chat_raw(
                messages=self.messages,
                tools=[tool.as_ollama_tool() for tool in self.tools.values()],
            )

            message = response.get("message", {})
            self.messages.append(message)
            last_content = message.get("content", "") or ""
            tool_calls = message.get("tool_calls") or []

            # Display model thinking
            if last_content:
                self._log_thinking("Model thinking", last_content)

            if not tool_calls:
                if wants_edit and not made_change:
                    self._log("[yellow]⚠️  Model didn't call edit tools, requesting patch creation...[/yellow]")
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

                self._log("[bold green]✅ Model completed task[/bold green]")
                return last_content

            self._log(f"[cyan]📞 Model called {len(tool_calls)} tool(s)[/cyan]")
            
            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name")
                args = self._parse_tool_args(fn.get("arguments") or {})

                self._log_tool_call(name, args)
                result = self.call_tool(name, args)
                used_tool = True

                edit_tools = {"write_file", "apply_patch", "edit_file"}
                success = self._tool_result_indicates_change(result) if name in edit_tools else True
                self._log_tool_result(name, result, success=success)

                if name in edit_tools and self._tool_result_indicates_change(result):
                    made_change = True
                    self._log("[bold green]✨ File modification successful![/bold green]")

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
                    self._log("[bold]📊 Getting git diff...[/bold]")
                    diff = self.call_tool("git_diff", {})
                    self._log(f"[green]Diff generated ({len(diff)} chars)[/green]")
                    self.messages.append(
                        {
                            "role": "tool",
                            "name": "git_diff",
                            "content": diff,
                        }
                    )
                    test_output = self._run_auto_test()
                    if test_output is not None:
                        self.messages.append(
                            {
                                "role": "tool",
                                "name": "auto_test",
                                "content": test_output,
                            }
                        )
                    return self._summarize_after_change(question, diff, test_output)

        if wants_edit and self.force_edit and not made_change:
            self._log("[yellow]⚠️  Force-generating patch as fallback...[/yellow]")
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

    def _preload_relevant_context(self, question: str, skip_large_contents: bool = False) -> list[str]:
        # Use faster file selection (skip embeddings) in interactive mode
        selected = auto_select_files(self.repo, question, max_files=self.auto_files, client=self.client)
        if not selected:
            selected = [f.rel_path for f in scan_repo(self.repo, max_files=self.auto_files)]

        # In interactive mode, skip loading full file contents to preserve context tokens
        if skip_large_contents:
            self._log(f"[dim]📦 Interactive preload: {len(selected)} files (names only)[/dim]")
            self.messages.append(
                {
                    "role": "tool",
                    "name": "auto_find_relevant_files",
                    "content": "\n".join(selected) if selected else "No relevant files found",
                }
            )
            self.messages.append(
                {
                    "role": "user",
                    "content": (
                        "Relevant files identified above. "
                        "If this is an edit task, use read_file to inspect specific files, then create a unified diff and call apply_patch."
                    ),
                }
            )
        else:
            # Full detailed context for initial non-interactive run, but cap the total
            # bytes so we don't blow past num_ctx. Files past the budget become
            # names-only — the model can still call read_file on them.
            total_budget = 80_000
            per_file_cap = 12_000
            self._log(f"[dim]📂 Loading context for {len(selected)} files (budget {total_budget} chars)...[/dim]")
            chunks: list[str] = []
            spent = 0
            included: list[str] = []
            deferred: list[str] = []
            for rel in selected:
                p = (self.repo / rel).resolve()
                if not p.exists() or not p.is_file():
                    continue
                try:
                    text = self._cached_read(p)
                except OSError:
                    continue
                if spent >= total_budget:
                    deferred.append(rel)
                    continue
                remaining = total_budget - spent
                cap = min(per_file_cap, remaining)
                truncated = text[:cap]
                marker = "\n[TRUNCATED]\n" if len(text) > cap else ""
                chunks.append(f"\n--- FILE: {rel} ---\n{truncated}{marker}")
                spent += len(truncated)
                included.append(rel)
            if deferred:
                chunks.append(
                    f"\n--- FILES DEFERRED (budget exhausted, call read_file as needed) ---\n"
                    + "\n".join(deferred)
                )
            context = "\n".join(chunks)
            self._log(
                f"[dim]✓ Loaded {spent} chars from {len(included)} files; "
                f"{len(deferred)} deferred[/dim]"
            )
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
        self._log("[bold yellow]🚨 FORCE PATCH MODE: Requesting unified diff directly[/bold yellow]")
        
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

        self._log("[bold]🤖 Generating unified diff from model...[/bold]")
        patch = self.client.generate(
            prompt,
            system=(
                SYSTEM_PROMPT
                + "\n\n"
                + PATCH_PROMPT
                + "\n\nYou must return a real patch for the requested code change."
            ),
            temperature=0.0,
        ).strip()

        if not self._looks_like_unified_diff(patch):
            self._log("[red]✗ Invalid patch format generated[/red]")
            patch_path = self.repo / ".local_code_assistant_last_response.txt"
            patch_path.write_text(patch, encoding="utf-8")
            return (
                "The model still did not produce a valid unified diff. "
                f"I saved its last response to {patch_path}.\n\n"
                f"Response:\n{patch}"
            )

        self._log(f"[green]✓ Valid diff generated ({len(patch)} chars)[/green]")
        result = self.call_tool("apply_patch", {"patch_content": patch})
        if not self._tool_result_indicates_change(result):
            self._log("[red]✗ Failed to apply patch[/red]")
            patch_path = self.repo / ".local_code_assistant_failed.patch"
            patch_path.write_text(patch, encoding="utf-8")
            return (
                "Generated a patch, but applying it failed. "
                f"Saved patch to {patch_path}.\n\n"
                f"Apply result:\n{result}\n\nPatch:\n{patch}"
            )

        self._log("[green]✓ Patch applied successfully[/green]")
        diff = self.call_tool("git_diff", {})
        return self._summarize_after_change(question, diff)

    def _looks_like_unified_diff(self, text: str) -> bool:
        return "diff --git " in text or ("--- " in text and "+++ " in text and "@@" in text)

    def _summarize_after_change(self, question: str, diff: str, test_output: str | None = None) -> str:
        if not diff.strip() or diff.strip() == "(no diff)":
            self._log("[red]⚠️  No diff detected - git repository check might be needed[/red]")
            return "A modification tool reported success, but git diff is empty. Check whether the target repo is a git repository."

        self._log(f"[green]📝 Generating summary of changes ({len(diff)} char diff)...[/green]")
        test_block = f"\nTest/build output after the change:\n{test_output}\n" if test_output else ""
        summary_prompt = f"""
                            Task:
                            {question}
                            Git diff produced by the agent:
                            {diff}
                            {test_block}
                            Summarize the actual file changes concisely. Mention that files were modified.
                            If test/build output is present, state whether it passed or failed and call out any failures.
                            """.strip()

        summary = self.client.generate(summary_prompt, system=SYSTEM_PROMPT)
        self._log("[bold green]✅ Task completed successfully![/bold green]")
        return summary

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
            text = self._cached_read(p)
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
            selected = auto_select_files(self.repo, question, max_files=max_files,client=self.client)
            return "\n".join(selected) if selected else "No relevant files found"

        def write_file(args: dict[str, Any]) -> str:
            p = self._safe_path(str(args["path"]))
            content = str(args["content"])
            if self.confirm_edits:
                before = p.read_text(encoding="utf-8") if p.exists() else ""
                self._show_preview(
                    title=f"Proposed write_file: {p.relative_to(self.repo)}",
                    before=before,
                    after=content,
                    label=str(p.relative_to(self.repo)),
                )
                if not self._prompt_accept():
                    return f"Write rejected by user: {p.relative_to(self.repo)}"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            self._invalidate_cache(p)
            return f"Wrote {p.relative_to(self.repo)} ({len(content)} bytes)"

        def edit_file(args: dict[str, Any]) -> str:
            path = str(args["path"])
            search = str(args["search"])
            replace = str(args["replace"])

            if not search:
                return "Edit failed: 'search' must be a non-empty string"

            p = self._safe_path(path)
            if not p.exists():
                return f"Edit failed: file not found: {path}"
            if not p.is_file():
                return f"Edit failed: not a regular file: {path}"

            original = p.read_text(encoding="utf-8")

            # Decide what the new content would be, without writing yet.
            new_content: str | None = None
            strategy: str = ""

            count = original.count(search)
            if count == 1:
                new_content = original.replace(search, replace, 1)
                strategy = "exact"
            elif count > 1:
                return (
                    f"Edit failed: 'search' matched {count} times in {path}. "
                    "Add more surrounding context so the match is unique."
                )
            else:
                norm_search = search.replace("\r\n", "\n").replace("\r", "\n")
                norm_original = original.replace("\r\n", "\n").replace("\r", "\n")
                n_count = norm_original.count(norm_search)
                if n_count == 1:
                    new_content = norm_original.replace(norm_search, replace.replace("\r\n", "\n"), 1)
                    strategy = "normalized line endings"
                elif n_count > 1:
                    return (
                        f"Edit failed: after normalizing line endings, 'search' still matched "
                        f"{n_count} times in {path}. Add more context."
                    )
                else:
                    return (
                        f"Edit failed: 'search' text not found in {path}. "
                        "Call read_file first to copy the exact text (including indentation and blank lines), "
                        "then retry edit_file with the precise match."
                    )

            if new_content == original:
                return f"Edit had no effect (search and replace produce identical text): {path}"

            if self.confirm_edits:
                self._show_preview(
                    title=f"Proposed edit_file ({strategy}): {path}",
                    before=original,
                    after=new_content,
                    label=path,
                )
                if not self._prompt_accept():
                    return f"Edit rejected by user: {path}"

            p.write_text(new_content, encoding="utf-8")
            self._invalidate_cache(p)
            return f"Edit applied ({strategy}): {path}"

        def apply_patch(args: dict[str, Any]) -> str:
            patch_content = str(args["patch_content"])
            dry_run = bool(args.get("dry_run", False))

            if patch_content.endswith(("\n\\", "\\n", '"')):
                self._log("[red]⚠️  PATCH TRUNCATION DETECTED[/red]")
                self._log(f"[red]Patch ends with suspicious character. Last 50 chars: {patch_content[-50:]!r}[/red]")

            if "\n@@" not in patch_content and ("--- a/" in patch_content or "--- " in patch_content):
                self._log("[yellow]⚠️  Patch appears incomplete (missing hunk headers)[/yellow]")

            patch_debug_path = self.repo / ".patch_debug.txt"
            patch_debug_path.write_text(patch_content, encoding="utf-8")
            self._log(f"[dim]📋 Patch saved to: {patch_debug_path}[/dim]")

            if self.confirm_edits and not dry_run:
                if HAS_RICH:
                    rprint(
                        Panel(
                            Syntax(patch_content, "diff", theme="monokai", line_numbers=False),
                            title=f"Proposed apply_patch ({len(patch_content)} bytes)",
                        )
                    )
                else:
                    print("=== Proposed apply_patch ===")
                    print(patch_content)
                if not self._prompt_accept():
                    return "Patch rejected by user"

            # Try a series of progressively more lenient strategies. The first one
            # that applies cleanly wins. Local LLMs frequently get hunk line counts
            # and context lines slightly wrong, so strict `git apply` is rarely enough.
            check_flag = ["--check"] if dry_run else []
            strategies: list[tuple[list[str], str]] = [
                (["git", "apply"] + check_flag + ["-"], "git-strict"),
                (["git", "apply", "--recount"] + check_flag + ["-"], "git-recount"),
                (
                    ["git", "apply", "--recount", "--ignore-whitespace"] + check_flag + ["-"],
                    "git-recount+ignore-whitespace",
                ),
            ]
            if not dry_run:
                # `patch` allows fuzz; `git apply` does not. Use it as final fallback
                # when running for real (it has no clean --check equivalent worth using).
                strategies.append(
                    (
                        ["patch", "-p1", "-l", "-F", "3", "--no-backup-if-mismatch", "--forward"],
                        "patch-fuzz3",
                    )
                )

            errors: list[str] = []
            for cmd, label in strategies:
                try:
                    result = subprocess.run(
                        cmd,
                        cwd=self.repo,
                        input=patch_content,
                        text=True,
                        capture_output=True,
                        timeout=60,
                    )
                except FileNotFoundError as exc:
                    errors.append(f"[{label}] command not available: {exc}")
                    continue
                if result.returncode == 0:
                    if not dry_run:
                        self._read_cache.clear()  # patch may touch many files; nuke whole cache.
                    verb = "Patch check passed" if dry_run else "Patch applied"
                    return f"{verb} (strategy: {label})"
                err = (result.stderr or result.stdout or "").strip()
                errors.append(f"[{label}] {err}")
                self._log(f"[yellow]✗ Strategy {label} failed: {err[:200]}[/yellow]")

            # `patch` writes .rej / .orig files on partial failure; sweep them so they
            # don't pollute the working tree or future git diffs.
            for leftover in list(self.repo.rglob("*.rej")) + list(self.repo.rglob("*.orig")):
                try:
                    leftover.unlink()
                except OSError:
                    pass

            joined = "\n".join(errors)
            return (
                f"Patch failed (all strategies, {len(patch_content)} bytes):\n{joined}\n"
                f"[DEBUG] saved to .patch_debug.txt — prefer edit_file with explicit search/replace for the next try."
            )

        def glob_files(args: dict[str, Any]) -> str:
            pattern = str(args["pattern"])
            base = str(args.get("base", "."))
            max_results = int(args.get("max_results", 200))
            if not pattern:
                return "Glob failed: 'pattern' must be a non-empty string"
            root = self._safe_path(base) if base not in ("", ".") else self.repo
            if not root.exists() or not root.is_dir():
                return f"Glob failed: base directory not found: {base}"
            matches: list[str] = []
            # `**` requires rglob; Path.glob handles plain * patterns. Use rglob if
            # the pattern contains ** so the model can write either style.
            iterator = root.rglob(pattern.replace("**/", "", 1)) if "**" in pattern else root.glob(pattern)
            for p in iterator:
                if not p.is_file():
                    continue
                try:
                    rel = p.relative_to(self.repo)
                except ValueError:
                    continue
                matches.append(str(rel))
                if len(matches) >= max_results:
                    break
            matches.sort()
            return "\n".join(matches) if matches else f"No files match: {pattern}"

        def search_text(args: dict[str, Any]) -> str:
            pattern = str(args["pattern"])
            path_arg = str(args.get("path", "."))
            max_results = int(args.get("max_results", 50))
            case_insensitive = bool(args.get("case_insensitive", False))
            fixed_string = bool(args.get("fixed_string", False))

            if not pattern:
                return "Search failed: 'pattern' must be a non-empty string"

            search_root = self._safe_path(path_arg) if path_arg not in ("", ".") else self.repo
            if not search_root.exists():
                return f"Search failed: path not found: {path_arg}"

            # Prefer ripgrep — fast, respects .gitignore, line-numbered.
            try:
                rg_cmd = ["rg", "--line-number", "--no-heading", "--color", "never",
                          "--max-count", str(max_results)]
                if case_insensitive:
                    rg_cmd.append("-i")
                if fixed_string:
                    rg_cmd.append("-F")
                rg_cmd.extend([pattern, str(search_root)])
                result = subprocess.run(rg_cmd, cwd=self.repo, capture_output=True, text=True, timeout=30)
                # rg exit codes: 0 = matches, 1 = no matches, 2 = error.
                if result.returncode in (0, 1):
                    out = result.stdout.strip()
                    return out or f"No matches for: {pattern}"
                # fall through to python on error
            except FileNotFoundError:
                pass  # ripgrep not installed

            # Python fallback: walk SOURCE files. Uses scan_repo so excludes are honored.
            try:
                flags = re.IGNORECASE if case_insensitive else 0
                regex = re.compile(re.escape(pattern) if fixed_string else pattern, flags)
            except re.error as exc:
                return f"Search failed: invalid regex: {exc}"

            matches: list[str] = []
            for f in scan_repo(self.repo, max_files=2000):
                full = self.repo / f.rel_path
                try:
                    text = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        # Trim very long lines so the model doesn't get walls of text.
                        snippet = line if len(line) <= 240 else line[:240] + " …"
                        matches.append(f"{f.rel_path}:{line_no}: {snippet}")
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break

            return "\n".join(matches) if matches else f"No matches for: {pattern}"

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
                ("find",)
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
                "edit_file",
                (
                    "PREFERRED tool for modifying an existing file. Replace one contiguous block "
                    "of text. 'search' must be an exact, unique substring of the current file "
                    "(copy it verbatim from read_file output, including indentation and blank lines). "
                    "'replace' is the new text. No line numbers, no diff headers. Call multiple "
                    "times for multiple separate edits."
                ),
                {
                    "type": "object",
                    "required": ["path", "search", "replace"],
                    "properties": {
                        "path": schema_string,
                        "search": schema_string,
                        "replace": schema_string,
                    },
                },
                edit_file,
            ),
            LocalTool(
                "apply_patch",
                (
                    "Last-resort tool. Apply a unified diff to the repository. Prefer edit_file "
                    "for normal edits — local models often miscount hunk line numbers, which makes "
                    "diffs fail. Use only when an edit truly spans many disjoint locations."
                ),
                {
                    "type": "object",
                    "required": ["patch_content"],
                    "properties": {"patch_content": schema_string, "dry_run": schema_boolean},
                },
                apply_patch,
            ),
            LocalTool(
                "glob_files",
                (
                    "List files matching a glob pattern (e.g. '**/*.py', 'src/*.cs'). "
                    "Use this when you know roughly what filenames you want; "
                    "use search_text when you need to locate content inside files."
                ),
                {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {
                        "pattern": schema_string,
                        "base": schema_string,
                        "max_results": schema_integer,
                    },
                },
                glob_files,
            ),
            LocalTool(
                "search_text",
                (
                    "Search the repository for a regex or fixed string. Returns "
                    "file:line: snippet for each match. Use this to locate symbols, "
                    "function names, error messages, or call sites before reading whole files."
                ),
                {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {
                        "pattern": schema_string,
                        "path": schema_string,
                        "max_results": schema_integer,
                        "case_insensitive": schema_boolean,
                        "fixed_string": schema_boolean,
                    },
                },
                search_text,
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
