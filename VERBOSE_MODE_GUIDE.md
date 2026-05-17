# Verbose Mode: Interactive Thinking Flow

## Overview

The **verbose mode** adds real-time console feedback showing the model's thinking and decision-making process during interactive sessions. This helps you understand what's happening at each step and debug agent behavior.

---

## Quick Start

### Enable Verbose Mode
```python
from local_code_assistant.agent import CodeAgent
from local_code_assistant.ollama_client import OllamaClient
from pathlib import Path

# Create agent with verbose=True
client = OllamaClient(model="mistral")
agent = CodeAgent(
    client=client,
    repo=Path("/my/repo"),
    verbose=True  # 👈 Enable console feedback
)

# Run interactive session
result = agent.run("Fix the bug in auth.py", keep_context=True)
result = agent.run("Add unit tests", keep_context=True)  # See feedback in console
```

---

## Console Output Breakdown

### Sample Interactive Session Output

```
📝 Continuing interactive session...
✏️  Edit request detected
📋 Task: Fix the authentication bug where login fails with special characters

🔍 Preloading relevant context...
📁 Found 3 relevant files:
   • src/auth.py
   • src/models.py
   • tests/test_auth.py
📦 Interactive preload: 3 files (names only)

⏳ Step 1/12
🤔 Waiting for model response...
💭 Model thinking: I need to examine the authentication module to identify 
   where special characters cause login failures. Let me start by reading 
   the auth.py file to understand the current implementation.

📞 Model called 2 tool(s)

🔧 Calling tool: read_file
   Args: {"path": "src/auth.py", "offset": 1, "limit": 150}
✓ Tool result: [line 1-150 of src/auth.py content shown]

🔧 Calling tool: read_file
   Args: {"path": "src/models.py", "offset": 30, "limit": 50}
✓ Tool result: [line 30-80 of src/models.py content shown]

⏳ Step 2/12
🤔 Waiting for model response...
💭 Model thinking: I found the issue! The regex pattern in the password 
   validation doesn't properly escape special characters. Line 45 has:
   `if not re.match(r'^[a-zA-Z0-9_]+$', password):`
   This will reject passwords with special characters. I'll fix this now.

📞 Model called 1 tool(s)

🔧 Calling tool: apply_patch
   Args: {"patch_content": "--- a/src/auth.py\n+++ b/src/auth.py\n..."}
✓ Tool result: Patch applied
✨ File modification successful!

📊 Getting git diff...
Diff generated (324 chars)

📝 Generating summary of changes (324 char diff)...
✅ Task completed successfully!
```

---

## Console Icons and Meanings

| Icon | Meaning | Example |
|------|---------|---------|
| 📝 | Message/State | "Continuing interactive session" |
| ✏️  | Edit request detected | Task requires code changes |
| 📋 | Task description | Shows the full user question |
| 🔍 | Searching/Preloading | Looking for relevant files |
| 📁 | Files found | List of identified files |
| 📦 | Context loading | Loading file contents |
| ⏳ | Step counter | Current step out of max steps |
| 🤔 | Model waiting | Agent awaits model response |
| 💭 | Model thinking | Displays model's reasoning |
| 📞 | Tool calls | Model requested N tools |
| 🔧 | Tool execution | Specific tool being called |
| ✓ | Success | Operation completed successfully |
| ✗ | Error/Failure | Operation failed |
| ✨ | File modified | Code change applied successfully |
| 📊 | Git operations | Git diff/status command |
| ⚠️  | Warning | Fallback path triggered |
| 🚨 | Critical | Force patch mode activated |
| 🤖 | Model generation | Model generating content |
| ✅ | Complete | Task finished successfully |

---

## What Gets Displayed

### 1. **Initialization & Setup**
```
📝 Continuing interactive session...
✏️  Edit request detected
📋 Task: [Your task description]
🔍 Preloading relevant context...
```

### 2. **File Discovery**
```
📁 Found 3 relevant files:
   • src/auth.py
   • src/models.py
   • tests/test_auth.py
📦 Interactive preload: 3 files (names only)
```

### 3. **Model Thinking**
```
⏳ Step 1/12
🤔 Waiting for model response...
💭 Model thinking: [First 200 chars of model's reasoning]
```

### 4. **Tool Calls**
```
📞 Model called 2 tool(s)
🔧 Calling tool: read_file
   Args: {"path": "src/auth.py", "offset": 1, "limit": 100}
✓ Tool result: [First 150 chars of result or summary]
```

### 5. **Code Modifications**
```
🔧 Calling tool: apply_patch
   Args: {"patch_content": "--- a/src/auth.py..."}
✓ Tool result: Patch applied
✨ File modification successful!
```

### 6. **Completion**
```
📊 Getting git diff...
Diff generated (456 chars)
✅ Task completed successfully!

[Final summary from model]
```

---

## Use Cases

### 1. **Debug Agent Behavior**
```python
# Find out why agent isn't making changes
agent = CodeAgent(client, repo, verbose=True)
result = agent.run("Add error handling", keep_context=True)
# See in console: exactly what the model is thinking and which tools it's calling
```

### 2. **Understand Model Reasoning**
```python
# Learn how the model approaches problems
agent = CodeAgent(client, repo, verbose=True)
result = agent.run("Optimize database queries", keep_context=True)
# Console shows: model's analysis, what files it reads, what changes it makes
```

### 3. **Monitor Long Sessions**
```python
# Track what's happening across multiple turns
agent = CodeAgent(client, repo, verbose=True, max_context_messages=15)
for question in questions:
    result = agent.run(question, keep_context=True)
    # See how context trimming happens
```

### 4. **Verify File Operations**
```python
# Watch each file read and modification
agent = CodeAgent(client, repo, verbose=True)
result = agent.run("Refactor the parser module", keep_context=True)
# Console shows: each file path accessed, content read, edits made
```

### 5. **Track Context Management**
```python
# See context growth and trimming in interactive mode
agent = CodeAgent(client, repo, verbose=True, max_context_messages=10)
result1 = agent.run("Fix bug 1", keep_context=True)
# Console: "📦 Interactive preload: N files (names only)"
result2 = agent.run("Fix bug 2", keep_context=True)
# Console shows context trimming happens automatically
```

---

## Performance Impact

### Speed
- **No noticeable slowdown** - logging is done asynchronously
- Output happens while model is processing
- No API call overhead

### Memory
- **Minimal increase** - only stores current session feedback
- Verbose logs don't persist between runs (unless you redirect to file)

### Verbosity Levels
```python
# Currently single level - all details shown
agent = CodeAgent(client, repo, verbose=True)

# To quiet it down, just use
agent = CodeAgent(client, repo, verbose=False)  # Default
```

---

## Console Colors and Styles

When Rich library is available, output includes:

- **[bold cyan]** - Important status messages
- **[yellow]** - Warnings and transitions
- **[green]** - Success statuses
- **[red]** - Errors
- **[blue]** - Step counters
- **[dim]** - Details and less important info
- **[cyan]** - Tool information

Example:
```
[bold cyan]🔧 Calling tool:[/bold cyan] [bold]read_file[/bold]
[green]✓ Tool result:[/] File contents displayed
```

If Rich is not installed, it degrades gracefully to plain text.

---

## Customizing Output

### Redirect to File
```python
import sys
from local_code_assistant.agent import CodeAgent

# Redirect verbose output to file
agent = CodeAgent(client, repo, verbose=True)

# In interactive session, capture output
with open("session.log", "w") as f:
    # This would need to redirect stdout/stderr
    result = agent.run(question, keep_context=True)
```

### Conditional Verbosity
```python
import os

verbose_mode = os.getenv("VERBOSE", "false").lower() == "true"
agent = CodeAgent(client, repo, verbose=verbose_mode)
```

Usage:
```bash
VERBOSE=true python my_script.py  # Enable verbose
python my_script.py                # Default quiet
```

---

## Troubleshooting

### No Output Appearing
1. Check `verbose=True` is set
2. Run a task with `keep_context=True`
3. Ensure stdout isn't redirected

### Too Much Output
1. Rich library limiting? It auto-truncates long outputs
2. Try restricting question length
3. Consider running quiet mode (`verbose=False`)

### Colors Not Showing
1. Rich not installed - falls back to plain text
2. Terminal doesn't support ANSI colors
3. Output redirected to file (redirect to terminal instead)

---

## Comparison: Verbose vs Quiet

### Quiet Mode (Default)
```python
agent = CodeAgent(client, repo, verbose=False)
result = agent.run(question, keep_context=True)
# Returns: Just the final result string
```

### Verbose Mode
```python
agent = CodeAgent(client, repo, verbose=True)
result = agent.run(question, keep_context=True)
# Displays: Full thinking process + returns result
```

---

## Advanced Usage

### Monitoring Specific Tasks
```python
agent = CodeAgent(client, repo, verbose=True)

print("\n" + "="*60)
print("REFACTORING PHASE")
print("="*60 + "\n")
result = agent.run("Refactor the database module", keep_context=True)
# See all thinking about refactoring

print("\n" + "="*60)
print("TESTING PHASE")
print("="*60 + "\n")
result = agent.run("Add comprehensive tests", keep_context=True)
# See all thinking about testing
```

### Performance Analysis
```python
import time

agent = CodeAgent(client, repo, verbose=True)

for i, question in enumerate(tasks, 1):
    print(f"\n[Task {i}] {question}")
    start = time.time()
    result = agent.run(question, keep_context=True)
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.1f}s")
```

### Debugging Failed Edits
```python
agent = CodeAgent(client, repo, verbose=True)
result = agent.run("Your edit task", keep_context=True)

# If it fails, console output shows:
# - What files were examined
# - What model thought
# - Which tools failed
# - Where the process stopped
```

---

## Summary

**Verbose mode is your window into the agent's mind.** It shows:
- ✅ Every file being read
- ✅ Model's reasoning
- ✅ Every tool call made  
- ✅ Success/failure of operations
- ✅ Context management
- ✅ Overall flow and progress

Enable it whenever you want to understand what's happening!

```python
agent = CodeAgent(client, repo, verbose=True)
```

