from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", ".idea", ".vs", ".venv", "venv", "node_modules", "bin", "obj", "target",
    "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

TEXT_EXTENSIONS = {
    ".cs", ".py", ".fs", ".fsx", ".sln", ".csproj", ".props", ".targets",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".md", ".txt", ".sql",
    ".sh", ".ps1", ".dockerfile", ".config", ".ini",
}

@dataclass(frozen=True)
class RepoFile:
    path: Path
    rel_path: str
    size: int


def scan_repo(repo: Path, max_files: int = 400) -> list[RepoFile]:
    repo = repo.resolve()
    files: list[RepoFile] = []
    for root, dirs, filenames in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES]
        for filename in filenames:
            path = Path(root) / filename
            if not is_text_candidate(path):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > 250_000:
                continue
            files.append(RepoFile(path=path, rel_path=str(path.relative_to(repo)), size=size))
            if len(files) >= max_files:
                return sorted(files, key=lambda f: f.rel_path)
    return sorted(files, key=lambda f: f.rel_path)


def is_text_candidate(path: Path) -> bool:
    if path.name.lower() in {"dockerfile", "makefile"}:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def read_files(repo: Path, rel_files: list[str], max_chars_per_file: int = 30_000) -> str:
    chunks: list[str] = []
    root = repo.resolve()
    for rel in rel_files:
        path = (root / rel).resolve()
        if not str(path).startswith(str(root)):
            raise ValueError(f"File escapes repo: {rel}")
        if not path.exists():
            chunks.append(f"\n--- FILE NOT FOUND: {rel} ---\n")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        truncated = text[:max_chars_per_file]
        marker = "\n[TRUNCATED]\n" if len(text) > max_chars_per_file else ""
        chunks.append(f"\n--- FILE: {rel} ---\n{truncated}{marker}")
    return "\n".join(chunks)


def git_diff(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout or result.stderr
    except Exception as exc:
        return f"Could not run git diff: {exc}"


def auto_select_files(repo: Path, question: str, max_files: int = 20) -> list[str]:
    files = scan_repo(repo)
    q = question.lower()
    scored: list[tuple[int, str]] = []
    tokens = [t for t in q.replace("_", " ").replace("-", " ").split() if len(t) >= 3]
    for f in files:
        rel_l = f.rel_path.lower()
        score = 0
        for t in tokens:
            if t in rel_l:
                score += 5
        if f.rel_path.endswith((".csproj", ".sln")):
            score += 2
        if "test" in rel_l:
            score += 1
        if score > 0:
            scored.append((score, f.rel_path))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [rel for _, rel in scored[:max_files]]
