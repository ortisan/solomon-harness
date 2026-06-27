# Git Operations and Branching Guidelines

This document outlines the version control standards for project development. All contributions must adhere to these policies.

## Branching Model

We follow a structured branching model to manage source code changes:

- **main**: The production branch containing stable and released code.
- **develop**: The integration branch for ongoing features. All feature branches merge here.
- **feature/<name>**: Short-lived branches created from develop to build new capabilities.
- **bugfix/<name>**: Short-lived branches created from develop to resolve issues.
- **release/<version>**: Branches created from develop to prepare a new release. They are merged back into main and develop.
- **hotfix/<version>**: Branches created from main to quickly patch critical production issues.

## Conventional Commits

Commit messages must follow the Conventional Commits specification. This standardizes version control history.

### Format

```
<type>(<scope>): <description>

[body]

[footer]
```

### Allowed Types

- **feat**: A new feature implementation.
- **fix**: A bug fix.
- **docs**: Documentation updates.
- **style**: Changes that do not affect the meaning of the code (formatting, missing semi-colons).
- **refactor**: Code restructuring that neither fixes a bug nor adds a feature.
- **perf**: Performance improvements.
- **test**: Adding missing tests or correcting existing tests.
- **build**: Changes that affect the build system or external dependencies.
- **ci**: Changes to CI configuration files and scripts.
- **chore**: Regular maintenance tasks.

### Message Rules

- Write the description in the imperative mood (e.g., "add test case" instead of "added test case").
- Do not include emojis, icons, or decorative elements.
- Keep the first line under 72 characters.
