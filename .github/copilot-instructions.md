# Copilot Instructions — IQ Samples

## Repository Structure

This is a **multi-sample repository**. Each sample folder at the repo root is a completely independent project with its own language, dependencies, configuration, and deployment target.

```
refund-agent-a365/   ← Python A365 agent + React dashboard
(future samples…)
```

## Critical Rules for Coding Agents

### 1. Stay in your lane
When working on a sample, **only read and modify files within that sample's folder**. Never cross-pollinate code, dependencies, environment variables, or configuration between samples.

### 2. Read the sample's copilot instructions first
Before making any changes to a sample, read its `.github/copilot-instructions.md` file for project-specific context — tech stack, key files, gotchas, and what not to touch.

### 3. Do not modify root-level governance files
Never modify these without explicit permission:
- `LICENSE`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`

### 4. Never commit secrets
- No API keys, tokens, connection strings, or credentials in code
- Use `.env.template` files with placeholder values for documentation
- Actual `.env` files are gitignored

### 5. Each sample is self-contained
- Each sample has its own `requirements.txt`, `package.json`, or equivalent
- Each sample has its own README with setup instructions
- Do not create shared libraries or cross-sample imports

### 6. Adding a new sample
When adding a new sample:
1. Create a new folder at the repo root
2. Include a `README.md` with setup and usage instructions
3. Include a `.github/copilot-instructions.md` with coding agent directions for that sample
4. Update the root `README.md` samples table
