# 🔧 Patch Truncation Detection & Debugging Guide

## Problem Identified

When the LLM (Ollama) calls `apply_patch`, patches are sometimes **truncated or incomplete**, causing errors like:
```
✗ Tool result: error: corrupt patch at line 16
```

This happens because:
1. **Limited console display** - only showing 300 chars truncates debugging info
2. **LLM generation issues** - model may truncate long patches
3. **JSON handling** - patches with special characters may be malformed
4. **Model context limits** - model may not have space to generate complete patches

---

## Improvements Made

### 1. **Enhanced Console Output for apply_patch**

When calling apply_patch, you now see:
```
🔧 Calling tool: apply_patch
   Patch size: 2456 chars
   ⚠️  Showing first 1500 chars:
   [Full patch content up to 1500 chars]
```

**Before:** Only showed 300 characters, truncating crucial patch information
**After:** Shows up to 1500 characters + patch size for debugging

### 2. **Better Error Reporting**

When a patch fails, you see:
```
✗ Patch result: FAILED
Error details:
error: corrupt patch at line 16
⚠️  Possible causes:
  1. Patch content is incomplete or truncated
  2. File paths in patch don't exist
  3. File content doesn't match patch expectations
  4. Patch format is invalid (missing headers, etc)
```

**Before:** Generic error messages with no context
**After:** Detailed diagnosis of possible issues

### 3. **Automatic Truncation Detection**

The system now detects:
- ✅ Patches ending with suspicious characters (`\n\`, `\n`, `"`)
- ✅ Patches missing hunk headers (`@@`)
- ✅ Incomplete diff structures

Example detection:
```
⚠️  PATCH TRUNCATION DETECTED
Patch ends with suspicious character. Last 50 chars:
[Shows the actual ending]
```

### 4. **Debug File Saving**

All patches are automatically saved to `.patch_debug.txt` in your repo:
```
📋 Patch saved to: /path/to/repo/.patch_debug.txt
```

You can then inspect the full patch content:
```bash
cat /path/to/repo/.patch_debug.txt
```

---

## How to Debug Patch Issues

### Step 1: Enable Verbose Mode
```python
agent = CodeAgent(client, repo, verbose=True)
result = agent.run(task, keep_context=True)
```

Or CLI:
```bash
local-code-assistant agent -i -v --repo .
```

### Step 2: Look for Patch Warnings

Watch for warnings like:
- `⚠️  PATCH TRUNCATION DETECTED`
- `⚠️  Patch appears incomplete`
- `⚠️  Showing first 1500 chars`

### Step 3: Check the Debug File

```bash
# View the full patch that was attempted
cat /repo/.patch_debug.txt

# Check if it's valid
git apply --check /repo/.patch_debug.txt

# Or see specific line that failed
sed -n '15,20p' /repo/.patch_debug.txt
```

### Step 4: Check Error Details

The error message now includes:
- Error line number
- What git apply thinks is wrong
- Patch file path for inspection

---

## Common Issues & Solutions

### Issue: "corrupt patch at line 16"

**Likely cause:** Patch is truncated

**Debug steps:**
1. Check console for `⚠️  PATCH TRUNCATION DETECTED`
2. View `.patch_debug.txt` to see actual content
3. Look for incomplete lines or missing `@@` headers

**Solution:**
- Give model more context
- Reduce file size for patch
- Ask model to generate smaller patches
- Increase Ollama context window

### Issue: "malformed patch"

**Likely cause:** Invalid patch format or encoding

**Debug steps:**
1. Check if patch has proper format: `--- a/file` and `+++ b/file`
2. Ensure no special characters are corrupted
3. Check hunk headers: `@@ -10,5 +10,6 @@`

**Solution:**
- Ask model to double-check patch format
- Validate patch structure before applying

### Issue: "No such file or directory"

**Likely cause:** File paths in patch don't match repository structure

**Debug steps:**
1. Check patch paths match your repo
2. Verify files exist in repository
3. Look at beginning of patch for correct file paths

**Solution:**
- Show model current directory structure
- Ensure file paths are correct

---

## Configuration Options

### Adjust Patch Display Size

In `agent.py`, line ~172:
```python
if len(patch) > 2000:  # Adjust this threshold
    patch_display = patch[:1500] + ...  # Adjust display size
```

### Disable Debug File Saving

Comment out lines 586-588 in `agent.py` if you don't want debug files.

### Change Debug File Location

Modify line 586 to save elsewhere:
```python
patch_debug_path = Path("/tmp/.patch_debug.txt")  # Different location
```

---

## Best Practices

### 1. **Use Verbose Mode During Development**
```python
agent = CodeAgent(client, repo, verbose=True)
```

### 2. **Review Patches Before Applying**
Ask model to generate with `dry_run=True` first:
```
Please generate a patch and call apply_patch with {"patch_content": "...", "dry_run": true}
```

### 3. **Keep Patches Reasonable**
- Patch one file at a time if possible
- Keep diffs < 500 lines
- Use multiple smaller patches vs. one large one

### 4. **Monitor Debug Files**
```bash
# Watch for new debug files
watch 'ls -la .patch_debug.txt'

# Compare multiple attempts
diff .patch_debug.txt.1 .patch_debug.txt.2
```

### 5. **Check Model Configuration**
If patches keep truncating:
- Increase Ollama `num-ctx` window
- Reduce input file sizes
- Use smaller model if possible
- Check model temperature (lower = more stable)

---

## What to Report if It Still Fails

If patches keep failing, collect this info:

```
1. Console output (save it):
   local-code-assistant agent -v --question "..." > debug.log 2>&1

2. Debug patch file:
   cat .patch_debug.txt

3. Repository info:
   git status
   ls -la
   echo $PWD

4. Model info:
   ollama list
   ollama show [model-name] | grep parameters

5. Full error:
   git apply --check .patch_debug.txt
   # Shows exact issue
```

---

## Summary

**The improvements help you:**

✅ See full patch content (up to 1500 chars instead of 300)
✅ Detect truncation automatically
✅ Understand why patches fail
✅ Inspect full patches in debug file
✅ Diagnose model/context issues

**Key files:**
- `.patch_debug.txt` - Full patch from last attempt
- Verbose console output - Real-time warnings
- Error details - Specific failure reasons

**Next steps if patches keep failing:**
1. Check `.patch_debug.txt` for actual content
2. Test patch manually: `git apply --check .patch_debug.txt`
3. Increase model context window in Ollama
4. Ask model to generate smaller patches
5. Check Ollama model capacity with debug info above

