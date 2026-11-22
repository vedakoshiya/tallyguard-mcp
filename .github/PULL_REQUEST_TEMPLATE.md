## Description

Please provide a summary of the changes and the problem/feature being addressed. Include relevant motivation and context.

Fixes #(issue)

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds read tools or draft types)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## TallyGuard MCP Governance Checklist

Please confirm that your pull request adheres to the core financial safety invariants:

- [ ] **Exact Decimal Currency Math**: All monetary amounts use `Decimal` with `ROUND_HALF_UP` (zero `float` arithmetic).
- [ ] **Draft-Only Mutation Invariant**: No direct write/alter operations to Tally have been added to any MCP tool.
- [ ] **Untrusted Text Isolation**: Any untrusted free-text from Tally (narrations, party names) is wrapped in `untrusted_text` containers.
- [ ] **Strict Pydantic Validation**: Models enforce `extra = "forbid"` and strict validation rules.
- [ ] **Test Coverage**: Added corresponding unit and integration tests under `tests/`.
- [ ] **Test Execution**: All 76+ tests pass with `pytest` locally.
- [ ] **No Real PII / Financial Data**: Test fixtures use only synthetic data (e.g. Surat textile references).
