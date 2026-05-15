# Local Code Assistant

Run against local Ollama:

```bash
ollama serve
ollama pull deepseek-coder:6.7b
python -m local_code_assistant.cli --model deepseek-coder:6.7b agent --repo /path/to/repo --question "Review this project"
```
