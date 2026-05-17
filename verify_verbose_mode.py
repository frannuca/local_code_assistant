#!/usr/bin/env python3
"""
Verification script to test verbose mode implementation
"""

import sys
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

def check_imports():
    """Verify all imports work"""
    print("✓ Checking imports...")
    try:
        from local_code_assistant.agent import CodeAgent
        from local_code_assistant.ollama_client import OllamaClient
        from local_code_assistant.repo import clear_embedding_cache
        print("  ✓ All imports successful")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False


def check_rich_library():
    """Check if Rich is available"""
    print("\n✓ Checking Rich library...")
    try:
        from rich import print as rprint
        from rich.console import Console
        print("  ✓ Rich library available (colors/emojis enabled)")
        return True
    except ImportError:
        print("  ⚠ Rich not found (will use plain text fallback)")
        return False


def check_verbose_parameter():
    """Check if CodeAgent accepts verbose parameter"""
    print("\n✓ Checking CodeAgent verbose parameter...")
    try:
        from local_code_assistant.agent import CodeAgent
        from local_code_assistant.ollama_client import OllamaClient, OllamaConfig
        
        # Create a mock client with config
        config = OllamaConfig(model="test", host="http://localhost:11434")
        client = OllamaClient(config)
        
        # Try to create agent with verbose=True
        agent = CodeAgent(
            client=client,
            repo=Path("."),
            verbose=True
        )
        
        # Check that verbose attribute exists
        assert hasattr(agent, 'verbose'), "Agent missing 'verbose' attribute"
        assert agent.verbose == True, "Verbose not set correctly"
        
        print("  ✓ verbose parameter works correctly")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def check_logging_methods():
    """Check if logging methods exist"""
    print("\n✓ Checking logging methods...")
    try:
        from local_code_assistant.agent import CodeAgent
        from local_code_assistant.ollama_client import OllamaClient, OllamaConfig
        
        config = OllamaConfig(model="test", host="http://localhost:11434")
        client = OllamaClient(config)
        agent = CodeAgent(client, Path("."), verbose=True)
        
        methods = [
            '_log',
            '_log_thinking',
            '_log_tool_call',
            '_log_tool_result',
            '_log_step',
            '_log_file_selected',
        ]
        
        for method in methods:
            if not hasattr(agent, method):
                print(f"  ✗ Missing method: {method}")
                return False
            if not callable(getattr(agent, method)):
                print(f"  ✗ Not callable: {method}")
                return False
        
        print(f"  ✓ All {len(methods)} logging methods present")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def check_cli_verbose_flag():
    """Check if CLI has verbose flag"""
    print("\n✓ Checking CLI verbose flag...")
    try:
        from local_code_assistant.cli import build_parser
        
        parser = build_parser()
        
        # Parse with verbose flag (goes before subcommand - it's a global flag)
        args = parser.parse_args(['--verbose', 'agent', '--repo', '.', '--question', 'test'])
        
        if not hasattr(args, 'verbose'):
            print("  ✗ CLI missing 'verbose' attribute")
            return False
        
        if args.verbose != True:
            print("  ✗ Verbose flag not set correctly")
            return False
        
        print("  ✓ CLI verbose flag works correctly (global flag)")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def check_syntax():
    """Verify Python syntax of modified files"""
    print("\n✓ Checking Python syntax...")
    try:
        import py_compile
        
        files = [
            'local_code_assistant/agent.py',
            'local_code_assistant/cli.py',
        ]
        
        for file in files:
            path = Path(__file__).parent / file
            if not path.exists():
                print(f"  ✗ File not found: {file}")
                return False
            
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as e:
                print(f"  ✗ Syntax error in {file}: {e}")
                return False
        
        print(f"  ✓ All {len(files)} files have valid Python syntax")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def check_documentation():
    """Check if documentation files exist"""
    print("\n✓ Checking documentation files...")
    
    docs = [
        'VERBOSE_MODE_GUIDE.md',
        'CLI_VERBOSE_USAGE.md',
        'VERBOSE_MODE_SUMMARY.md',
        'VERBOSE_MODE_QUICK_REF.md',
        'verbose_mode_demo.py',
    ]
    
    base = Path(__file__).parent
    missing = []
    
    for doc in docs:
        if not (base / doc).exists():
            missing.append(doc)
    
    if missing:
        print(f"  ✗ Missing {len(missing)} documentation files: {missing}")
        return False
    
    print(f"  ✓ All {len(docs)} documentation files present")
    return True


def main():
    """Run all checks"""
    print("\n" + "=" * 60)
    print("🔧 VERBOSE MODE IMPLEMENTATION VERIFICATION")
    print("=" * 60 + "\n")
    
    checks = [
        ("Imports", check_imports),
        ("Rich Library", check_rich_library),
        ("Verbose Parameter", check_verbose_parameter),
        ("Logging Methods", check_logging_methods),
        ("CLI Verbose Flag", check_cli_verbose_flag),
        ("Python Syntax", check_syntax),
        ("Documentation", check_documentation),
    ]
    
    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60 + "\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All checks passed! Verbose mode is ready to use.")
        print("\nUsage:")
        print("  Python:  agent = CodeAgent(client, repo, verbose=True)")
        print("  CLI:     local-code-assistant agent -i -v --repo .")
        return 0
    else:
        print(f"\n⚠️  {total - passed} check(s) failed. Please review above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

