# Contributing to TallyGuard MCP

Thank you for your interest in contributing to TallyGuard MCP!

## Code of Conduct

All contributors are expected to uphold a welcoming, professional, and respectful environment.

## Ground Rules for Contributions

Because TallyGuard MCP is a financial governance system:

1. **No Floating Point for Currency**: All currency values must use Python's `Decimal` or integer paise. Never use Python `float`.
2. **Never Add Direct Writes to Tally in MCP Tools**: MCP tools must only generate drafts. Direct write-paths to Tally must remain behind the authenticated out-of-band approval engine.
3. **Always Validate Inputs**: Tools and API routes must enforce strict JSON Schema and Pydantic validation with `extra = 'forbid'`.
4. **Never Commit Secrets or Fixtures with Real Data**: All test fixtures must use synthetic company records.

## Development Workflow

1. Fork the repository and create your feature branch from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Set up the development environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

3. Run linting, type checks, and tests:
   ```bash
   ruff check .
   mypy server bridge tests
   pytest
   ```

4. Commit your changes with descriptive commit messages and submit a Pull Request.
