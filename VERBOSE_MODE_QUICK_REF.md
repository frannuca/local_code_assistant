# Verbose Mode - Quick Reference Card

## Enable Verbose Mode

### Python Code
```python
agent = CodeAgent(client, repo, verbose=True)
result = agent.run(question, keep_context=True)
```

### Command Line
```bash
local-code-assistant agent -i -v --repo .
```

---

## What You'll See

### File Discovery
```
🔍 Preloading relevant context...
📁 Found 3 relevant files:
   • src/auth.py
   • src/models.py
   • tests/test_auth.py
```

### Model Thinking
```
⏳ Step 1/12
🤔 Waiting for model response...
💭 Model thinking: I need to examine...
```

### Tool Calls
```
📞 Model called 2 tool(s)
🔧 Calling tool: read_file
   Args: {"path": "src/auth.py"}
✓ Tool result: [contents...]
```

### Code Changes
```
🔧 Calling tool: apply_patch
✨ File modification successful!
✅ Task completed successfully!
```

---

## Console Icons

| Icon | Means |
|------|-------|
| 📝 | Message/update |
| ✏️  | Edit requested |
| 📋 | Task shown |
| 🔍 | Searching files |
| 📁 | Files found |
| 📦 | Loading context |
| ⏳ | Progress (step N/M) |
| 🤔 | Model thinking |
| 💭 | Model's reasoning |
| 📞 | Tools called |
| 🔧 | Tool executing |
| ✓ | Success |
| ✨ | File changed |
| 📊 | Git diff |
| ✅ | Complete |

---

## Common Patterns

### Interactive Session
```bash
local-code-assistant agent -i -v
# Follow with questions
agent> Fix the bug
agent> Add tests
agent> /exit
```

### One-Shot Task
```bash
local-code-assistant agent -v --question "Remove debug code" --repo .
```

### Debugging
```bash
local-code-assistant agent -v --question "Problem task" --repo . --max-steps 5
# See where it fails
```

### Python Interactive Loop
```python
agent = CodeAgent(client, repo, verbose=True, max_context_messages=15)

questions = [
    "Task 1",
    "Task 2", 
    "Task 3",
]

for q in questions:
    print(f"\n>>> {q}")
    result = agent.run(q, keep_context=True)
    print(f"Result: {result}\n")
```

---

## Options

### CodeAgent Parameters
```python
CodeAgent(
    client=client,           # Ollama client
    repo=Path("."),          # Repository path
    verbose=True,            # Enable feedback ← NEW
    keep_context=True,       # Keep history
    max_context_messages=20, # Trim at this size
)
```

### CLI Flags
```bash
-v, --verbose              Enable console feedback
-i, --interactive          Interactive REPL mode
--repo PATH                Repository (default: .)
--question QUESTION        Question to ask
--model MODEL              Ollama model
--max-steps N              Maximum steps (default: 20)
```

---

## What Gets Logged

✅ Session initialization
✅ Edit detection
✅ File discovery
✅ File content loading
✅ Model's thinking process
✅ Tool calls made
✅ Tool results
✅ File modifications
✅ Git operations
✅ Context trimming
✅ Task completion

---

## Understanding Steps

```
⏳ Step 1/12   Step 1 of 12 maximum attempts
⏳ Step 2/12   Model thinks → calls tools
⏳ Step 3/12   Tools execute → results returned
...
✅ Complete   Task finished before max steps
```

---

## Off by Default

```python
# Normal mode - no feedback
agent = CodeAgent(client, repo)
result = agent.run(question)

# Verbose mode - see everything
agent = CodeAgent(client, repo, verbose=True)
result = agent.run(question)
```

---

## No Performance Penalty

- ✅ No noticeable slowdown
- ✅ Logging happens async
- ✅ Doesn't block execution
- ✅ Minimal memory overhead

---

## Use Cases

- 🎯 **Understand behavior** - See what model is doing
- 🎯 **Debug issues** - Find where it gets stuck
- 🎯 **Learn patterns** - Observe problem-solving approach
- 🎯 **Monitor tasks** - Track progress through complex work
- 🎯 **Verify operations** - Confirm files are being modified
- 🎯 **Track context** - Watch automatic trimming

---

## Keyboard Commands (Interactive)

```
agent> question text          Ask a question
agent> /clear                 Clear context
agent> /exit                  Exit session
Ctrl+C                        Interrupt
Ctrl+D                        Exit (EOF)
```

---

## Getting Help

```bash
local-code-assistant agent --help
local-code-assistant --help

# Or read the guides:
cat VERBOSE_MODE_GUIDE.md
cat CLI_VERBOSE_USAGE.md
```

---

## Example Session

```bash
$ local-code-assistant agent -i -v --repo my-repo

[Verbose shows file discovery...]

agent> Fix authentication bug
[Verbose shows model thinking, tool calls, edits...]
✅ Done

agent> Add unit tests  
[Verbose shows context trimming, new analysis...]
✅ Done

agent> Optimize queries
[Verbose shows bounded context in action...]
✅ Done

agent> /exit
```

---

## Common Issues

**No output?**
→ Check `verbose=True` is set
→ Run a task (needs execution to show output)

**Too much output?**
→ That's normal! It's showing you everything
→ Use quiet mode: don't add `--verbose` flag

**Colors not showing?**
→ Terminal might not support ANSI
→ Rich library auto-degrades to plain text

---

## Key Features ⭐

1. **Real-time feedback** - See what's happening
2. **Model thinking** - Display model's reasoning
3. **Tool tracking** - Watch tool selection/execution
4. **File monitoring** - See files being read/modified
5. **Progress indicator** - Current step / total steps
6. **Context management** - Display trimming in action
7. **Status emoji** - Quick visual status indicators
8. **Rich formatting** - Colors and emojis (if available)
9. **Graceful degradation** - Works without Rich library
10. **Zero overhead** - No performance penalty

---

## Status

✅ **Production Ready**
✅ **Fully tested**
✅ **Fully documented**
✅ **Backward compatible**

