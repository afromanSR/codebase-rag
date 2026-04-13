# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x     | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it via [GitHub Security Advisories](https://github.com/afromanSR/codebase-rag/security/advisories/new).

**Do not open a public issue for security vulnerabilities.**

## Scope

codebase-rag runs locally and processes local files. Security concerns include:

- Path traversal in file walking (reading files outside the workspace)
- Arbitrary command execution via config files
- Sensitive data exposure through indexed content
- MCP stdio transport integrity

We take these seriously and will respond to reports within 7 days.
