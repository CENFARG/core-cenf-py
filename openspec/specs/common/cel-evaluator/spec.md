---
Spec_ID: SPEC_CEL
Title: Common CEL Evaluator Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [cel, expression, sandboxed, pycel, aot]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_CEL: Common CEL Evaluator

## Purpose

Provide a sandboxed CEL (Common Expression Language) expression evaluator using `pycel` (Apache 2.0). Consumed by FeatureFlagManager, DynamicPromptingManager, and AlertManager for conditional evaluation. AOT validation during bootstrap ensures fail-fast.

## Python API

```python
from typing import Any

def evaluate_cel(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate a CEL expression against a context. Sandboxed — no I/O or system access."""
    ...

def validate_cel(expression: str) -> list[str]:
    """AOT-compile a CEL expression. Return list of errors (empty if valid)."""
    ...
```

## Consumer Matrix

| Manager | CEL Usage | Example Expression |
|---------|-----------|-------------------|
| FeatureFlagManager (M12) | Targeting rules | `context.environment == "prod" && context.tenant_id == "cntrs"` |
| DynamicPromptingManager (M14) | Prompt assembly conditions | `session_state.intent == "refund"` |
| AlertManager (M15) | Alert trigger conditions | `error_rate > 0.05 && circuit_state == "OPEN"` |

## Gherkin Scenarios

### Scenario: Simple equality evaluation

- WHEN `evaluate_cel('context.environment == "prod"', {"environment": "prod"})` is called
- THEN it returns `True`

### Scenario: Compound expression with AND

- WHEN `evaluate_cel('context.a > 5 && context.b < 10', {"a": 7, "b": 3})` is called
- THEN it returns `True`

### Scenario: Expression evaluates to False

- WHEN `evaluate_cel('context.x == "yes"', {"x": "no"})` is called
- THEN it returns `False`

### Scenario: AOT validation catches syntax error

- WHEN `validate_cel('context.x == ')` is called (incomplete expression)
- THEN it returns a non-empty list with at least one error string

### Scenario: AOT validation passes valid expression

- WHEN `validate_cel('context.x > 0')` is called
- THEN it returns an empty list `[]`

### Scenario: Sandboxed — no system access

- WHEN `evaluate_cel('__import__("os").system("echo hack")', {})` is called
- THEN it raises an error or returns False (sandboxed — no code execution)
- AND no system command is executed

### Scenario: Missing context key

- WHEN `evaluate_cel('context.missing_key == "value"', {})` is called
- THEN it returns `False` (missing key evaluates as falsy)
- AND no exception is raised

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Invalid CEL syntax | VALIDATION | Return from validate_cel() |
| pycel not installed | PERMANENT | Fail bootstrap |
| Expression evaluation error | VALIDATION | Return False, log warning |

## RED Metrics

None — this is a shared utility module. Consumers (M12, M14, M15) emit their own metrics.

## Test Requirements

- **Unit**: Test evaluate_cel with various expressions, validate_cel with valid/invalid input.
- **Integration**: Verify sandboxed execution (no eval/exec, no system access).
- **E2E**: FeatureFlagManager, DynamicPromptingManager, and AlertManager all use this module correctly.

## Do's and Don'ts

**Do**:
- Use pycel (Apache 2.0) for sandboxed CEL evaluation
- Compile expressions AOT during bootstrap (fail-fast on syntax errors)
- Return False for missing context keys (graceful degradation)

**Don't**:
- Use Python's eval() or exec() (critical injection vector)
- Allow I/O access during expression evaluation
- Raise exceptions on evaluation errors — return False instead
