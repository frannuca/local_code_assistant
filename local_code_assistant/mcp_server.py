"""MCP server providing tools for filesystem, git, and code operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastmcp.server import FastMCP

from .repo import (
    auto_select_files,
    auto_select_files_by_embeddings,
    read_files,
    scan_repo,
)
server = FastMCP("local-code-assistant")
_repo_root: Path | None = None


def set_repo_root(repo: Path) -> None:
    """Set the repository root for tool operations."""
    global _repo_root
    _repo_root = repo.resolve()


def get_repo_root() -> Path:
    """Get the current repository root."""
    global _repo_root
    if _repo_root is None:
        _repo_root = Path.cwd().resolve()
    return _repo_root


def _ensure_relative(path_str: str) -> Path:
    """Convert a path string to a Path relative to repo root."""
    path = Path(path_str)
    if path.is_absolute():
        return path
    return get_repo_root() / path


@server.tool()
def read_file(path: str, offset: int | None = None, limit: int | None = None) -> str:
    """Read file contents with optional line range."""
    full_path = _ensure_relative(path)
    if not full_path.exists():
        return f"File not found: {full_path}"
    if not full_path.is_file():
        return f"Not a file: {full_path}"

    content = full_path.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    if offset is None:
        offset = 1
    if offset < 1:
        offset = 1
    start_idx = offset - 1
    end_idx = len(lines) if limit is None else min(start_idx + limit, len(lines))

    selected_lines = lines[start_idx:end_idx]
    result_lines = []
    for i, line in enumerate(selected_lines, start=offset):
        result_lines.append(f"{i:5d} | {line}")

    return "\n".join(result_lines)


@server.tool()
def list_files(path: str = ".", recursive: bool = True, max_files: int = 400) -> str:
    """List files in directory or scan entire repository."""
    full_path = _ensure_relative(path)
    if not full_path.exists():
        return f"Path not found: {full_path}"
    if full_path.is_file():
        return f"Is a file: {full_path}"

    result = []
    count = 0

    if recursive:
        files = scan_repo(get_repo_root(), max_files=max_files)
        for f in files:
            result.append(f"{f.rel_path}: {f.size} bytes")
    else:
        for item in sorted(full_path.iterdir()):
            if item.is_dir():
                result.append(f"{item.name}/ (directory)")
            else:
                try:
                    size = item.stat().st_size
                    result.append(f"{item.name}: {size} bytes")
                except OSError:
                    result.append(f"{item.name}: (cannot stat)")
            count += 1
            if count >= max_files:
                break

    return "\n".join(result) if result else "No files found"


@server.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    full_path = _ensure_relative(path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return f"Wrote file: {full_path} ({len(content)} bytes)"


@server.tool()
def append_file(path: str, content: str) -> str:
    """Append content to a file."""
    full_path = _ensure_relative(path)
    existing = ""
    if full_path.exists():
        existing = full_path.read_text(encoding="utf-8", errors="replace")

    full_path.parent.mkdir(parents=True, exist_ok=True)
    new_content = existing + content
    full_path.write_text(new_content, encoding="utf-8")
    return f"Appended to file: {full_path} ({len(content)} bytes added)"


@server.tool()
def delete_file(path: str) -> str:
    """Delete a file."""
    full_path = _ensure_relative(path)
    if not full_path.exists():
        return f"File not found: {full_path}"
    if full_path.is_dir():
        return f"Cannot delete directory: {full_path}"

    full_path.unlink()
    return f"Deleted file: {full_path}"


@server.tool()
def file_exists(path: str) -> str:
    """Check if a file or directory exists."""
    full_path = _ensure_relative(path)
    if full_path.exists():
        if full_path.is_dir():
            return f"Exists (directory): {full_path}"
        else:
            size = full_path.stat().st_size
            return f"Exists (file): {full_path} ({size} bytes)"
    else:
        return f"Does not exist: {full_path}"


def _run_git(args: list[str]) -> str:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=get_repo_root(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout or result.stderr
        return output if output else "(no output)"
    except Exception as exc:
        return f"Error running git: {exc}"


@server.tool()
def git_diff(file: str | None = None, staged: bool = False) -> str:
    """Get git diff of uncommitted changes."""
    cmd = ["diff"]
    if staged:
        cmd.append("--cached")
    cmd.append("--")
    if file:
        cmd.append(file)
    return _run_git(cmd)


@server.tool()
def git_status() -> str:
    """Show git status of the repository."""
    return _run_git(["status", "--porcelain"])


@server.tool()
def git_log(n: int = 10, oneline: bool = True) -> str:
    """Show recent git commits."""
    cmd = ["log", f"-{n}"]
    if oneline:
        cmd.append("--oneline")
    return _run_git(cmd)


@server.tool()
def git_add(files: list[str]) -> str:
    """Stage files for commit."""
    if not files:
        return "No files specified to add"
    return _run_git(["add"] + files)


@server.tool()
def git_commit(message: str) -> str:
    """Create a git commit."""
    if not message:
        return "Commit message is required"
    return _run_git(["commit", "-m", message])


@server.tool()
def git_show(ref: str, file: str | None = None) -> str:
    """Show details of a specific commit or file at a commit."""
    cmd = ["show", ref]
    if file:
        cmd.extend(["--", file])
    return _run_git(cmd)


@server.tool()
def scan_repository(max_files: int = 400) -> str:
    """Scan the repository and list all text files."""
    files = scan_repo(get_repo_root(), max_files=max_files)
    lines = [f"Found {len(files)} files:"]
    for f in files:
        lines.append(f"  {f.rel_path}: {f.size} bytes")
    return "\n".join(lines)


@server.tool()
def read_multiple_files(files: list[str], max_chars_per_file: int = 30000) -> str:
    """Read content from multiple files at once."""
    if not files:
        return "No files specified"
    return read_files(get_repo_root(), files, max_chars_per_file=max_chars_per_file)


@server.tool()
def search_files(pattern: str, directory: str = ".") -> str:
    """Search for files matching patterns."""
    full_path = _ensure_relative(directory)
    if not full_path.exists():
        return f"Directory not found: {full_path}"

    matching = []
    try:
        for item in full_path.rglob(pattern):
            if item.is_file():
                matching.append(str(item.relative_to(get_repo_root())))
    except Exception as exc:
        return f"Search error: {exc}"

    return "\n".join(matching) if matching else "No matches found"


@server.tool()
def auto_find_relevant_files(question: str, max_files: int = 20) -> str:
    """Select relevant files based on cosine similarity between question embedding and file path/content embeddings."""
    if not question:
        return "Question is required"

    try:
        selected = auto_select_files_by_embeddings(
            get_repo_root(),
            question,
            max_files=max_files,
            candidate_limit=300,
            embedding_model="nomic-embed-text",
            ollama_host="http://localhost:11434",
        )

        lines = [f"Selected {len(selected)} files by embedding similarity:"]
        for path, score in selected:
            lines.append(f"  {score:.4f}  {path}")

        return "\n".join(lines)

    except Exception as exc:
        selected = auto_select_files(get_repo_root(), question, max_files=max_files)
        lines = [
            f"Embedding selection failed: {exc}",
            f"Falling back to lexical selection. Selected {len(selected)} files:",
        ]
        lines.extend(f"  {f}" for f in selected)
        return "\n".join(lines)

@server.tool()
def edit_file(path: str, search: str, replace: str) -> str:
    """
    Modify an existing file by exact search-and-replace.

    `search` must be a unique contiguous substring of the current file (copy it
    verbatim from read_file output, including indentation). The first matching
    occurrence is replaced with `replace`. Falls back to a line-ending-normalized
    match if the strict match fails.

    This is the PREFERRED edit primitive for local LLMs — no line numbers, no
    hunk headers. Use apply_patch only when an edit spans many files.
    """
    if not search:
        return "Edit failed: 'search' must be a non-empty string"

    full_path = _ensure_relative(path)
    if not full_path.exists():
        return f"Edit failed: file not found: {full_path}"
    if not full_path.is_file():
        return f"Edit failed: not a regular file: {full_path}"

    original = full_path.read_text(encoding="utf-8", errors="replace")

    count = original.count(search)
    if count == 1:
        full_path.write_text(original.replace(search, replace, 1), encoding="utf-8")
        return f"Edit applied (exact): {path}"
    if count > 1:
        return (
            f"Edit failed: 'search' matched {count} times in {path}. "
            "Add more surrounding context so the match is unique."
        )

    norm_search = search.replace("\r\n", "\n").replace("\r", "\n")
    norm_original = original.replace("\r\n", "\n").replace("\r", "\n")
    n_count = norm_original.count(norm_search)
    if n_count == 1:
        new = norm_original.replace(norm_search, replace.replace("\r\n", "\n"), 1)
        full_path.write_text(new, encoding="utf-8")
        return f"Edit applied (normalized line endings): {path}"
    if n_count > 1:
        return (
            f"Edit failed: after normalizing line endings, 'search' still matched "
            f"{n_count} times in {path}. Add more context."
        )

    return (
        f"Edit failed: 'search' text not found in {path}. "
        "Call read_file first to copy the exact text (including indentation and blank lines), "
        "then retry edit_file with the precise match."
    )


@server.tool()
def apply_patch(patch_content: str, dry_run: bool = False) -> str:
    """Apply a unified diff patch to the repository."""
    if not patch_content:
        return "Patch content is required"

    patch_content = patch_content.strip()

    if not patch_content.startswith("diff --git "):
        return (
            "Invalid patch: patch must be a complete unified git diff starting with 'diff --git'. "
            "Regenerate the full patch."
        )

    cmd = ["git", "apply"]
    if dry_run:
        cmd.append("--check")
    cmd.append("-")

    result = subprocess.run(
        cmd,
        cwd=get_repo_root(),
        input=patch_content,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0:
        return "Patch validated successfully" if dry_run else "Patch applied successfully"

    return (
        f"Patch failed:\n{result.stderr}\n\n"
        "The patch was not applied. Regenerate a complete unified diff. "
        "Do not truncate the patch. Include full file paths, complete hunk headers, "
        "and all changed lines."
    )

