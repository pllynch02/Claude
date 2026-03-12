# CLAUDE.md — AI Assistant Guide for `pllynch02/Claude`

This file provides AI coding assistants (Claude Code and similar tools) with
everything needed to understand, develop, and maintain this repository
effectively.

---

## Repository Overview

| Field       | Value                              |
|-------------|------------------------------------|
| Name        | Claude                             |
| Owner       | pllynch02                          |
| Remote      | pllynch02/Claude                   |
| Status      | Initialized — no source files yet  |

This repository was created as a fresh git project. Update this section as the
project's purpose and technology stack are established.

---

## Git Workflow

### Branch Naming

All AI-assistant feature branches **must** follow this pattern:

```
claude/<slug>-<session-id>
```

Example: `claude/claude-md-mmms3qklztd188th-L4jyM`

> Pushes to branches that do not match the `claude/` prefix or that use the
> wrong session ID will fail with HTTP 403.

### Standard Flow

```bash
# 1. Create (or check out) the designated branch
git checkout -b claude/<slug>-<session-id>

# 2. Make changes, stage selectively
git add <specific-files>   # never `git add -A` for untrusted content

# 3. Commit with a clear message
git commit -m "feat: <short description>"

# 4. Push with upstream tracking
git push -u origin claude/<slug>-<session-id>
```

### Push Retry Policy

If `git push` fails due to a **network error**, retry with exponential backoff:

| Attempt | Wait before retry |
|---------|-------------------|
| 1       | 2 s               |
| 2       | 4 s               |
| 3       | 8 s               |
| 4       | 16 s              |

Do **not** retry on HTTP 403/401 — those are authorization failures that require
human intervention.

### Commit Message Convention

Follow the [Conventional Commits](https://www.conventionalcommits.org/) spec:

```
<type>(<optional scope>): <short summary>

[optional body]

[optional footer(s)]
```

Common types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`

---

## Development Guidelines

### Code Style

- Prefer clarity over cleverness.
- Avoid over-engineering: only add what the task requires.
- Do not add docstrings, comments, or type annotations to code you did not
  change.
- Do not introduce backwards-compatibility shims for code that is simply being
  removed.

### Security

- Never commit secrets, credentials, `.env` files, or API keys.
- Validate input only at system boundaries (user input, external APIs).
- Avoid command injection, SQL injection, XSS, and other OWASP Top 10 issues.
- If insecure code is introduced accidentally, fix it immediately in the same
  session.

### File Operations

- Prefer editing existing files over creating new ones.
- Do not create documentation files (`.md`, `README`) unless explicitly
  requested.
- Before deleting or overwriting files, confirm the action with the user when
  the operation is irreversible.

---

## Risky Actions — Confirm Before Proceeding

The following operations require explicit user confirmation before execution:

| Category           | Examples                                              |
|--------------------|-------------------------------------------------------|
| Destructive ops    | `rm -rf`, `git reset --hard`, dropping tables         |
| Force operations   | `git push --force`, `git rebase -i` without review    |
| Shared state       | Pushing to shared branches, posting to external APIs  |
| Credential changes | Modifying auth config, rotating secrets               |

---

## Updating This File

When new technology, tooling, or conventions are added to the project, update
the relevant sections of this file **in the same PR** as the change. Sections
to keep current:

- Repository Overview (purpose, stack)
- Project Structure (once source files exist)
- Build & Test Commands
- Environment Variables / Configuration

---

## Placeholder Sections

The sections below should be filled in once the project is bootstrapped.

### Project Structure

```
(to be documented once source files are added)
```

### Build & Test Commands

```bash
# Install dependencies
# (add command here, e.g., npm install / pip install -r requirements.txt)

# Run tests
# (add command here, e.g., npm test / pytest)

# Lint / format
# (add command here, e.g., npm run lint / ruff check .)

# Build / compile
# (add command here, e.g., npm run build / cargo build)
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| (none defined yet) | — | — |

### Key Dependencies

| Package | Purpose |
|---------|---------|
| (none defined yet) | — |
