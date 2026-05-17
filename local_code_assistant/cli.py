from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from local_code_assistant.agent import CodeAgent
from local_code_assistant.ollama_client import OllamaClient, OllamaConfig
from local_code_assistant.prompts import PATCH_PROMPT, SYSTEM_PROMPT
from local_code_assistant.repo import auto_select_files, git_diff, read_files, scan_repo

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local code assistant using Ollama")
    parser.add_argument("--model", default="qwen3-coder:30b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose console feedback")

    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Scan repository files")
    p_index.add_argument("--repo", default=".")
    p_index.add_argument("--max-files", type=int, default=400)

    p_ask = sub.add_parser("ask", help="Ask a one-shot question about a repository")
    p_ask.add_argument("--repo", default=".")
    p_ask.add_argument("--question", required=True)
    p_ask.add_argument("--files", nargs="*", default=[])
    p_ask.add_argument("--auto-files", type=int, default=20)

    p_patch = sub.add_parser("patch", help="Generate a patch proposal without applying it")
    p_patch.add_argument("--repo", default=".")
    p_patch.add_argument("--question", required=True)
    p_patch.add_argument("--files", nargs="*", default=[])
    p_patch.add_argument("--auto-files", type=int, default=20)
    p_patch.add_argument("--out", default="proposal.patch")

    p_diff = sub.add_parser("diff", help="Show git diff")
    p_diff.add_argument("--repo", default=".")

    p_agent = sub.add_parser("agent", help="Run tool-calling code agent")
    p_agent.add_argument("--repo", default=".")
    p_agent.add_argument("--question", default=None)
    p_agent.add_argument("--max-steps", type=int, default=100)
    p_agent.add_argument("--auto-files", type=int, default=60)
    p_agent.add_argument("--no-force-edit", action="store_true", help="Do not fallback to patch generation/application")
    p_agent.add_argument("--confirm", "-c", action="store_true", help="Ask for confirmation before each file modification, showing a diff preview")
    p_agent.add_argument("--auto-test", action="store_true", help="After each successful edit, run pytest / dotnet build / npm test and feed the result to the model")
    p_agent.add_argument("--interactive", "-i", action="store_true", help="Keep asking questions in a REPL with accumulated context")
    p_agent.add_argument("--clear-command", default="/clear", help="Command that clears interactive context")
    p_agent.add_argument("--exit-command", default="/exit", help="Command that exits interactive mode")

    return parser


def make_client(args: argparse.Namespace) -> OllamaClient:
    return OllamaClient(
        OllamaConfig(
            model=args.model,
            host=args.host,
            temperature=args.temperature,
            num_ctx=args.num_ctx,
        )
    )


def cmd_index(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    files = scan_repo(repo, max_files=args.max_files)
    table = Table(title=f"Repository index: {repo}")
    table.add_column("File")
    table.add_column("Size", justify="right")
    for f in files:
        table.add_row(f.rel_path, str(f.size))
    console.print(table)


def resolve_files(repo: Path, provided: list[str], question: str, auto_count: int, client:Optional[OllamaClient]) -> list[str]:
    if provided:
        return provided
    selected = auto_select_files(repo, question, max_files=auto_count,client=client)
    if not selected:
        selected = [f.rel_path for f in scan_repo(repo, max_files=auto_count)]
    return selected


def cmd_ask(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    files = resolve_files(repo, args.files, args.question, args.auto_files, client=make_client(args))
    context = read_files(repo, files)
    prompt = f"""
                Repository: {repo}
                Selected files:
                {chr(10).join('- ' + f for f in files)}
                
                User question:
                {args.question}
                
                Code context:
                {context}
                """.strip()
    console.print(f"[bold]Selected files:[/bold] {', '.join(files)}")
    answer = make_client(args).generate(prompt, system=SYSTEM_PROMPT)
    console.print(answer)


def cmd_patch(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    files = resolve_files(repo, args.files, args.question, args.auto_files, client=make_client(args))
    context = read_files(repo, files)
    prompt = f"""
Repository: {repo}
Selected files:
{chr(10).join('- ' + f for f in files)}

Task:
{args.question}

Code context:
{context}
""".strip()
    console.print(f"[bold]Selected files:[/bold] {', '.join(files)}")
    patch = make_client(args).generate(prompt, system=SYSTEM_PROMPT + "\n\n" + PATCH_PROMPT)
    out = Path(args.out)
    out.write_text(patch, encoding="utf-8")
    console.print(f"Patch proposal written to [bold]{out}[/bold]")
    console.print("Apply manually with:")
    console.print(f"  git apply {out}")


def cmd_diff(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    console.print(git_diff(repo))


def cmd_agent(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    client = make_client(args)
    agent = CodeAgent(
        client=client,
        repo=repo,
        max_steps=args.max_steps,
        auto_files=args.auto_files,
        force_edit=not args.no_force_edit,
        verbose=args.verbose,
        confirm_edits=args.confirm,
        auto_test=args.auto_test,
    )

    if args.interactive:
        console.print(f"[bold]Interactive agent[/bold] repo={repo}")
        console.print(f"Type [bold]{args.clear_command}[/bold] to clear context, [bold]{args.exit_command}[/bold] to exit.")
        if args.verbose:
            console.print(f"[dim]Verbose mode: ON [Use --verbose/-v to disable][/dim]")
        if args.question:
            console.print(agent.run(args.question, keep_context=True))

        while True:
            try:
                question = console.input("\n[bold cyan]agent>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\nExiting.")
                return

            if not question:
                continue
            if question == args.exit_command:
                return
            if question == args.clear_command:
                agent.reset_context()
                console.print("Context cleared.")
                continue

            answer = agent.run(question, keep_context=True)
            console.print(answer)
        return

    if not args.question:
        raise SystemExit("agent requires --question unless --interactive is used")

    answer = agent.run(args.question, keep_context=False)
    console.print(answer)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "index":
        cmd_index(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "patch":
        cmd_patch(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "agent":
        cmd_agent(args)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
