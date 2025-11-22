# PowerShell Commands for Manual Application

## Prerequisites
- Windows PowerShell 5.1 or higher
- Python 3.12+ installed
- Git installed
- Repository cloned to local machine

## Step 1: Navigate to Project and Setup

```powershell
# Navigate to your local repository clone
cd C:\path\to\bipolar-api

# Verify you're in the correct directory
Get-Location
# Should show: C:\path\to\bipolar-api

# Check current branch
git branch
# Should show: * main (or your current branch)
```

## Step 2: Create and Activate Virtual Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate

# Verify activation (prompt should show (.venv))
Write-Host "Virtual environment activated" -ForegroundColor Green

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
python -m pip install -r requirements.txt
```

## Step 3: Verify Baseline (Optional but Recommended)

```powershell
# Run tests to capture baseline
python -m pytest -q > pytest-baseline.txt 2>&1

# View results
Get-Content pytest-baseline.txt | Select-String "passed.*failed"

# Expected output should show failures like:
# 74 passed, 83 failed, 14 warnings in XX.XXs
```

## Step 4: Apply Changes

### Option A: Using Git (Recommended)

```powershell
# Fetch latest changes
git fetch origin

# Checkout the fix branch
git checkout fix/auto-auth-client-20251122-153152

# Or merge the fix branch into your current branch
# git merge fix/auto-auth-client-20251122-153152
```

### Option B: Manual Changes

If you prefer to apply changes manually:

#### Change 1: Update .gitignore

```powershell
# Add .venv to .gitignore
Add-Content -Path .gitignore -Value "`n.venv/"

# Verify
Get-Content .gitignore | Select-String "\.venv"
```

#### Change 2: Update api/dependencies.py

```powershell
# Backup the original file
Copy-Item api\dependencies.py api\dependencies.py.backup

# Open in your editor (choose one):
notepad api\dependencies.py
# Or: code api\dependencies.py  (if using VS Code)
# Or: notepad++ api\dependencies.py
```

**Manual Edit Instructions:**
After line 9 (after `logger = logging.getLogger("bipolar-api.dependencies")`), add these lines:

```python
# Re-export acreate_client to support test mocking
# Tests need to patch api.dependencies.acreate_client for dependency injection
__all__ = ['acreate_client', 'AsyncClient', 'Client', 'get_supabase_client', 
           'get_supabase_anon_auth_client', 'get_supabase_service_role_client',
           'get_supabase_service', 'verify_admin_authorization', 'get_admin_emails']
```

#### Change 3: Update data_generator.py

```powershell
# Backup the original file
Copy-Item data_generator.py data_generator.py.backup

# Open in your editor
notepad data_generator.py
# Or: code data_generator.py
```

**Manual Edit Instructions:**
Find line 298 (should contain `raise HTTPException(status_code=500, detail="Falha após todas as tentativas")`).

Change it to:
```python
    raise HTTPException(status_code=500, detail="Falha após todas as tentativas (duplicate key)")
```

## Step 5: Verify Changes

```powershell
# Verify acreate_client is now accessible
python -c "import api.dependencies; print('acreate_client accessible:', hasattr(api.dependencies, 'acreate_client'))"

# Expected output: acreate_client accessible: True
```

## Step 6: Run Tests

```powershell
# Run all tests
python -m pytest -q > pytest-after-fix.txt 2>&1

# Display results
Get-Content pytest-after-fix.txt | Select-String "passed"

# Expected output:
# 157 passed, 2 warnings in X.XXs
```

## Step 7: Compare Before and After

```powershell
# Create a comparison summary
Write-Host "`n==================== TEST RESULTS COMPARISON ====================" -ForegroundColor Cyan
Write-Host "`nBEFORE FIX:" -ForegroundColor Red
Get-Content pytest-baseline.txt | Select-String "passed.*failed"

Write-Host "`nAFTER FIX:" -ForegroundColor Green
Get-Content pytest-after-fix.txt | Select-String "passed"

Write-Host "`n=================================================================" -ForegroundColor Cyan
```

## Step 8: Run Specific Test Categories (Optional)

```powershell
# Test admin endpoints
python -m pytest tests/test_admin_endpoints.py -v

# Test account endpoints
python -m pytest tests/test_account_endpoints.py -v

# Test predictions endpoints
python -m pytest tests/test_predictions_endpoint.py -v

# Test data generator retry logic
python -m pytest tests/test_data_generator_retry.py::TestCreateUserWithRetry::test_failure_after_max_retries -v
```

## Step 9: Commit Changes (If Applied Manually)

```powershell
# Stage changes
git add .gitignore api\dependencies.py data_generator.py

# Commit with descriptive message
git commit -m "fix(deps): re-export acreate_client to support test patching

- Add __all__ to api/dependencies.py to export acreate_client
- Update error message in data_generator.py to include 'duplicate key'
- Add .venv to .gitignore

Fixes 83 test failures. All 157 tests now pass."

# Push to remote (if you have a feature branch)
# git push origin your-branch-name
```

## Rollback Instructions

If you need to undo the changes:

### Git Rollback (Recommended)

```powershell
# If you haven't committed yet
git checkout -- .gitignore api\dependencies.py data_generator.py

# If you've committed
git log --oneline -5  # Find the commit hash
git revert <commit-hash>

# If you checked out the fix branch
git checkout main
```

### Manual Rollback

```powershell
# Restore from backups
Copy-Item api\dependencies.py.backup api\dependencies.py -Force
Copy-Item data_generator.py.backup data_generator.py -Force

# Remove .venv line from .gitignore manually or:
$content = Get-Content .gitignore | Where-Object { $_ -notmatch "^\.venv" }
Set-Content .gitignore -Value $content
```

## Troubleshooting

### Issue: "python: command not found"
```powershell
# Check if Python is installed
python --version

# If not found, install Python or use py launcher
py -3.12 --version
```

### Issue: "Activate.ps1 cannot be loaded because running scripts is disabled"
```powershell
# Run as Administrator
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then retry activation
.\.venv\Scripts\Activate
```

### Issue: Tests still failing after applying changes
```powershell
# Verify changes were applied correctly
python -c "import api.dependencies; print('__all__' in dir(api.dependencies))"
# Should print: True

# Check if dependencies are installed
pip list | Select-String "supabase"
# Should show: supabase 2.x.x

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Issue: Git merge conflicts
```powershell
# Check status
git status

# If conflicts in modified files
# Manually resolve conflicts in your editor, then:
git add <resolved-files>
git commit
```

## Verification Checklist

Use this checklist to ensure all changes are correctly applied:

```powershell
# Run verification script
$checks = @(
    @{
        Name = "Virtual environment exists"
        Test = { Test-Path .venv }
    },
    @{
        Name = ".venv in .gitignore"
        Test = { (Get-Content .gitignore) -match "\.venv" }
    },
    @{
        Name = "acreate_client exported"
        Test = { 
            python -c "import api.dependencies; exit(0 if hasattr(api.dependencies, 'acreate_client') else 1)"
            $LASTEXITCODE -eq 0
        }
    },
    @{
        Name = "Dependencies installed"
        Test = { 
            python -c "import supabase, pytest, fastapi; exit(0)"
            $LASTEXITCODE -eq 0
        }
    },
    @{
        Name = "All tests passing"
        Test = {
            python -m pytest -q --tb=no 2>&1 | Out-Null
            $LASTEXITCODE -eq 0
        }
    }
)

Write-Host "`n==================== VERIFICATION CHECKLIST ====================" -ForegroundColor Cyan
foreach ($check in $checks) {
    $result = & $check.Test
    $status = if ($result) { "✓ PASS" } else { "✗ FAIL" }
    $color = if ($result) { "Green" } else { "Red" }
    Write-Host "$status - $($check.Name)" -ForegroundColor $color
}
Write-Host "=================================================================" -ForegroundColor Cyan
```

## Additional Resources

- **Full Report:** See `report_change.md` for detailed analysis
- **Test Output:** Check `pytest-after.txt` for complete test results
- **Git Branch:** `fix/auto-auth-client-20251122-153152`
- **Related Issue:** Fixes 83 pytest failures

## Support

If you encounter issues not covered here:
1. Check `report_change.md` for detailed troubleshooting
2. Verify Python version: `python --version` (should be 3.12+)
3. Ensure all dependencies are installed: `pip list`
4. Check for uncommitted changes: `git status`

---

**Last Updated:** 2025-11-22  
**Compatible with:** Windows 10/11, PowerShell 5.1+, Python 3.12+
