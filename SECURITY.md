# Security Policy

## Reporting Security Issues

If you discover a security vulnerability in this project, please report it by emailing the maintainers. Do not create public GitHub issues for security vulnerabilities.

## Secret Management

This project uses environment variables for sensitive configuration. Follow these best practices:

### For Developers

1. **Never commit secrets to the repository**
   - The `.env` file is gitignored and should contain your local secrets
   - Use `.env.example` as a template
   - Copy `.env.example` to `.env` and fill in your actual credentials

2. **Environment Variables Required**
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_SERVICE_KEY`: Your Supabase service role key

3. **Pre-commit Hooks (Recommended)**
   ```bash
   # Install pre-commit
   pip install pre-commit
   
   # Setup hooks
   pre-commit install
   
   # Run manually
   pre-commit run --all-files
   ```

4. **Local Secret Scanning**
   You can manually scan for secrets using the following commands:
   ```bash
   # Scan for high-entropy strings
   grep -rEn "['\"][A-Za-z0-9+/]{60,}[=]{0,2}['\"]" --include="*.py" .
   
   # Check that .env is gitignored
   grep "^\.env$" .gitignore
   ```

### For Deployment (Render, Railway, etc.)

Set environment variables in your deployment platform's dashboard:
- Navigate to your project settings
- Add environment variables
- Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
- Never commit these values to code

## Automated Security

### GitHub Actions Workflow

This repository includes a GitHub Actions workflow (`.github/workflows/secret-scan.yml`) that:

1. **Runs Gitleaks** - Scans git history for leaked secrets
2. **Scans for high-entropy strings** - Detects potential API keys and tokens
3. **Pattern matching** - Checks for common secret patterns (API_KEY, PASSWORD, TOKEN, etc.)
4. **Validates .gitignore** - Ensures .env files are properly excluded
5. **Checks .env.example** - Verifies it doesn't contain real secrets

The workflow runs on:
- Push to `main`, `develop`, or `security/**` branches
- Pull requests to `main` or `develop`

### What to Do If Secrets Are Detected

If the secret scanning workflow detects a potential secret:

1. **Immediately rotate the exposed credentials**
   - Generate new API keys/tokens
   - Update your deployment environment variables
   - Update your local `.env` file

2. **Remove the secret from git history**
   ```bash
   # For recent commits (not yet pushed)
   git reset --soft HEAD~1
   git commit -m "Remove exposed secrets"
   
   # For commits already pushed (use with caution)
   # Consider using tools like BFG Repo-Cleaner or git-filter-repo
   ```

3. **Verify the secret is removed**
   ```bash
   git log --all --full-history -S "your-secret-pattern"
   ```

4. **Report the incident** to the repository maintainers

## Key Rotation Policy

- **Immediate rotation** if a secret is committed or exposed
- **Regular rotation** (every 90 days) for production credentials
- **Post-incident rotation** after any security event

## Dependencies Security

- Regularly update dependencies to patch known vulnerabilities
- Monitor security advisories for Python packages
- Use `pip-audit` or similar tools to check for vulnerable packages

## Additional Resources

- [Supabase Security Best Practices](https://supabase.com/docs/guides/platform/going-into-prod)
- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
