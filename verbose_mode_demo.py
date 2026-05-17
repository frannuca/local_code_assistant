#!/usr/bin/env python3
"""
Demo: Interactive Mode with Verbose Thinking Flow
Shows how to enable console feedback during model interaction
"""

from pathlib import Path
from local_code_assistant.agent import CodeAgent
from local_code_assistant.ollama_client import OllamaClient

# Example usage - this is what you would run:
def main():
    # Initialize with verbose=True to see thinking flow
    client = OllamaClient(model="mistral", host="http://localhost:11434")
    repo = Path("/path/to/your/repo")

    # Create agent with verbose feedback enabled
    agent = CodeAgent(
        client=client,
        repo=repo,
        verbose=True,  # 🎯 Enable detailed console feedback
        max_context_messages=20,
    )

    print("=" * 60)
    print("🎯 Interactive Mode with Verbose Thinking Flow")
    print("=" * 60)
    print()

    # First turn - fresh context
    print("[1] First question - full context loading:\n")
    question1 = "Fix the authentication bug in auth.py where login fails for users with special characters in passwords"
    result1 = agent.run(question1, keep_context=True)
    print(f"\n✅ Result:\n{result1}\n")

    print("\n" + "=" * 60 + "\n")

    # Second turn - interactive continuation with bounded context
    print("[2] Follow-up question - bounded context (will be trimmed):\n")
    question2 = "Now add unit tests for the authentication fix"
    result2 = agent.run(question2, keep_context=True)
    print(f"\n✅ Result:\n{result2}\n")

    print("\n" + "=" * 60 + "\n")

    # Third turn - continues with bounded context
    print("[3] Third question - maintains bounded context:\n")
    question3 = "Optimize the password validation function to be more efficient"
    result3 = agent.run(question3, keep_context=True)
    print(f"\n✅ Result:\n{result3}\n")


def show_console_output_example():
    """Show what the console output looks like"""
    print("""
Example Console Output with verbose=True:

────────────────────────────────────────────────────────────────
📝 Continuing interactive session...
✏️  Edit request detected
📋 Task: Fix the authentication bug
🔍 Preloading relevant context...
📁 Found 3 relevant files:
   • src/auth.py
   • tests/test_auth.py
   • src/models.py
📦 Interactive preload: 3 files (names only)
⏳ Step 1/12
🤔 Waiting for model response...
💭 Model thinking: Let me analyze the authentication bug. I need to examine the 
   password validation logic and see where special characters cause issues...
📞 Model called 2 tool(s)
🔧 Calling tool: read_file
   Args: {"path": "src/auth.py", "offset": 1, "limit": 100}
✓ Tool result: File content with line numbers...
🔧 Calling tool: read_file
   Args: {"path": "src/models.py", "offset": 50, "limit": 50}
✓ Tool result: File content...
⏳ Step 2/12
🤔 Waiting for model response...
💭 Model thinking: I found the issue! The regex pattern doesn't handle special 
   characters properly. I'll fix it now...
📞 Model called 1 tool(s)
🔧 Calling tool: apply_patch
   Args: {"patch_content": "--- a/src/auth.py\\n+++ b/src/auth.py\\n@@..."}
✓ Tool result: Patch applied
✨ File modification successful!
📊 Getting git diff...
Diff generated (456 chars)
📝 Generating summary of changes (456 char diff)...
✅ Task completed successfully!

────────────────────────────────────────────────────────────────

Console Icon Legend:
  📝 = Message/state change
  ✏️  = Edit request detected  
  📋 = Task description
  🔍 = Searching/preloading
  📁 = Files found
  📦 = Context loading
  ⏳ = Step counter
  🤔 = Model thinking
  💭 = Model reasoning display
  📞 = Tool calls made
  🔧 = Tool execution
  ✓ = Success
  ✗ = Error/failure
  ✨ = Modification success
  📊 = Git operations
  ✅ = Task complete
    """)


if __name__ == "__main__":
    print("\n" + "🎯 " * 20)
    print("VERBOSE INTERACTIVE MODE DEMO")
    print("🎯 " * 20 + "\n")

    print("📖 EXAMPLE CONSOLE OUTPUT:\n")
    show_console_output_example()

    print("\n" + "=" * 80)
    print("To use verbose mode in your code:")
    print("=" * 80 + "\n")

    print("""
from local_code_assistant.agent import CodeAgent
from local_code_assistant.ollama_client import OllamaClient
from pathlib import Path

# Create agent with verbose=True
client = OllamaClient(model="mistral")
agent = CodeAgent(
    client=client,
    repo=Path("/my/repo"),
    verbose=True  # 👈 Enable verbose output!
)

# Run with keep_context=True for interactive mode
result = agent.run("Your task here", keep_context=True)
    """)

    print("\n" + "=" * 80)
    print("Features:")
    print("=" * 80)
    print("""
✅ See every step of the agent's thinking process
✅ Watch model reasoning in real-time  
✅ Track tool calls and their results
✅ Monitor context trimming in interactive mode
✅ Useful for debugging agent behavior
✅ Great for understanding what's happening
✅ Helps identify when model is struggling
✅ Shows file loading and context management

Parameters:
  verbose=True       - Enable detailed console feedback (default: False)
  keep_context=True  - Keep conversation context across turns (default: False)
    """)

