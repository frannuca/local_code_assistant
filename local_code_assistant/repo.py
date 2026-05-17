from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from local_code_assistant import ollama_client
from local_code_assistant.ollama_client import OllamaClient

DEFAULT_EXCLUDES = {
    ".git", ".idea", ".vs", ".venv", "venv", "node_modules", "bin", "obj", "target",
    "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

TEXT_EXTENSIONS = {
    ".cs", ".py", ".fs", ".fsx", ".sln", ".csproj", ".props", ".targets",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".md", ".txt", ".sql",
    ".sh", ".ps1", ".dockerfile", ".config", ".ini",
}

SOURCE_EXTENSIONS = {
    # Python
    ".py",

    # C / C++
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx",

    # C# / .NET
    ".cs",

    # Java / JVM
    ".java", ".kt", ".kts", ".scala", ".gradle",

    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",

}


SPECIAL_SOURCE_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "CMakeLists.txt",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
}

@dataclass(frozen=True)
class RepoFile:
    path: Path
    rel_path: str
    size: int

import json
import math
import urllib.request


# Simple in-memory cache for embeddings
_embedding_cache: dict[str, list[float]] = {}


def ollama_embed(
    text: str,
    model: str = "nomic-embed-text",
    host: str = "http://localhost:11434",
    use_cache: bool = True,
) -> list[float]:
    # Use cache to avoid re-embedding identical text
    cache_key = f"{model}:{text[:100]}"  # Use text prefix as key
    if use_cache and cache_key in _embedding_cache:
        return _embedding_cache[cache_key]
    
    url = f"{host.rstrip('/')}/api/embeddings"

    payload = {
        "model": model,
        "prompt": text,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))

    embedding = body["embedding"]
    if use_cache:
        _embedding_cache[cache_key] = embedding
    return embedding


def clear_embedding_cache() -> None:
    """Clear the embedding cache (useful before new tasks or to free memory)."""
    global _embedding_cache
    _embedding_cache = {}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)

def file_llm_summarizer(content:str,client:Optional[OllamaClient]=None) -> str:
    return content if client is None else client.chat( [
        {
            "role": "system",
            "content": "Summarize the provided file content in 1-2 sentences, focusing on the main purpose and functionality of the file. Be concise and informative.",
        },
        {
            "role": "user",
            "content": f"File Content to Analyze: {content}"
        }
    ])

def build_file_context(path: Path, repo_root: Path, max_chars: int = 40000, client:Optional[OllamaClient]=None) -> str:
    rel_path = str(path.relative_to(repo_root))

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""

    # Use beginning of file. Usually contains imports, class names, method names.
    content = content[:max_chars] if client is None else file_llm_summarizer(content, client=client)

    return f"""
            FILE: {rel_path}\nCONTENT:{content}""".strip()


def auto_select_files_by_embeddings(
    repo_root: Path,
    question: str,
    max_files: int = 20,
    candidate_limit: int = 250,
    embedding_model: str = "nomic-embed-text",
    ollama_host: str = "http://localhost:11434",
    client: Optional[OllamaClient] = None
) -> list[tuple[str, float]]:
    """
    Select relevant files by cosine similarity between:
    - question embedding
    - file path + partial file content embedding
    
    If skip_embeddings=True, just return files by name relevance (faster for interactive mode).
    """

    files = scan_repo(repo_root, max_files=candidate_limit)


    question_embedding = ollama_embed(
        question,
        model=embedding_model,
        host=ollama_host,
    )

    scored: list[tuple[str, float]] = []

    for file_info in files:
        path = repo_root / file_info.rel_path
        if not path.exists() or not path.is_file():
            continue
        suffix = path.suffix.lower()
        is_source_file = suffix in SOURCE_EXTENSIONS
        if not is_source_file:
            continue

        context = build_file_context(path, repo_root, client=client)
        file_embedding = ollama_embed(
            context,
            model=embedding_model,
            host=ollama_host,
        )
        score = cosine_similarity(question_embedding, file_embedding)
        scored.append((file_info.rel_path, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    return scored[:max_files]

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
    return (path.suffix.lower() in TEXT_EXTENSIONS) or (path.suffix.lower() in SOURCE_EXTENSIONS)


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



_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def _tokenize(text: str) -> set[str]:
    # Split on non-alphanumerics so 'auth_handler' yields {'auth', 'handler'}.
    return set(_TOKEN_RE.findall(text.lower()))


def _lexical_select_files(repo: Path, question: str, max_files: int) -> list[str]:
    """Cheap fallback: score files by overlap between question tokens and file path tokens."""
    tokens = _tokenize(question)
    if not tokens:
        return [f.rel_path for f in scan_repo(repo, max_files=max_files)]
    scored: list[tuple[str, int]] = []
    for f in scan_repo(repo, max_files=400):
        overlap = len(tokens & _tokenize(f.rel_path))
        if overlap > 0:
            scored.append((f.rel_path, overlap))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [rel for rel, _ in scored[:max_files]]


def auto_select_files(repo: Path, question: str, max_files: int = 50, client: Optional[OllamaClient] = None) -> list[str]:
    try:
        scored = auto_select_files_by_embeddings(repo, question, max_files=max_files, client=client)
        return [rel for rel, _ in scored[:max_files]]
    except Exception:
        # Embedding server unavailable, model missing, etc. Don't crash the agent.
        return _lexical_select_files(repo, question, max_files=max_files)
