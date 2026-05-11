# Coding Standards

## Overview

This document establishes Python-specific coding standards and practices for enterprise software development. Adherence to these standards ensures code maintainability, consistency across teams, and reduces technical debt. This guide covers style conventions, tooling configuration, documentation requirements, and quality assurance practices specific to Python development environments.

## Style and Formatting Standards

### PEP 8 Compliance

All Python code must conform to PEP 8 (Python Enhancement Proposal 8), the official style guide for Python code. The following requirements are mandatory:

- **Line length**: Maximum 88 characters (using Black formatter standard)
- **Indentation**: 4 spaces per indentation level, no tabs
- **Naming conventions**:
  - Variables and functions: `lowercase_with_underscores`
  - Classes: `PascalCase`
  - Constants: `UPPERCASE_WITH_UNDERSCORES`
  - Private methods/attributes: prefix with single underscore `_private_method`
  - Dunder methods: `__method__` for special Python methods only

### Code Formatting Configuration

Configure your development environment with automatic formatting tools:

```ini
# pyproject.toml - Black configuration
[tool.black]
line-length = 88
target-version = ['py39']
include = '\.pyi?$'
exclude = '''
/(
    \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | _build
  | buck-out
  | build
  | dist
)/
'''
```

### Import Organization

Organize imports according to PEP 8 with three distinct groups, separated by blank lines:

```python
# Standard library imports
import os
import sys
from datetime import datetime
from typing import List, Optional

# Third-party imports
import requests
from flask import Flask, render_template

# Local application imports
from myapp.models import User
from myapp.utils import validate_email
```

## Code Quality and Linting

### Static Analysis Tools

Implement automated code quality checks using the following tools:

| Tool | Purpose | Configuration File |
|------|---------|-------------------|
| pylint | Comprehensive code analysis | `.pylintrc` |
| flake8 | PEP 8 style enforcement | `.flake8` |
| mypy | Static type checking | `mypy.ini` |
| bandit | Security vulnerability scanning | `.bandit` |

### Linting Configuration Example

```ini
# .flake8 - Flake8 configuration
[flake8]
max-line-length = 88
extend-ignore = E203, W503
exclude =
    .git,
    __pycache__,
    docs/source/conf.py,
    .venv,
    build,
    dist
per-file-ignores =
    __init__.py:F401
```

### Pre-commit Hooks

Enforce code standards before commits using pre-commit framework:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.1.0
    hooks:
      - id: black
        language_version: python3.9

  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=88']

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.1
    hooks:
      - id: mypy
        additional_dependencies: ['types-all']

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ['-c', '.bandit']
```

## Type Hints and Annotations

### Mandatory Type Annotations

All functions must include type hints for parameters and return values:

```python
from typing import List, Dict, Optional, Union

def process_user_data(
    user_ids: List[int],
    include_metadata: bool = False
) -> Dict[int, Dict[str, str]]:
    """
    Process user data and return formatted results.
    
    Args:
        user_ids: List of user identifiers to process
        include_metadata: Whether to include metadata in results
        
    Returns:
        Dictionary mapping user IDs to their data
        
    Raises:
        ValueError: If user_ids list is empty
    """
    if not user_ids:
        raise ValueError("user_ids cannot be empty")
    
    results: Dict[int, Dict[str, str]] = {}
    # Implementation here
    return results
```

### Complex Type Definitions

Use TypedDict and Protocol for complex structures:

```python
from typing import TypedDict, Protocol

class UserRecord(TypedDict):
    """Type definition for user database records."""
    id: int
    username: str
    email: str
    created_at: str
    is_active: bool

class DataProcessor(Protocol):
    """Protocol for data processing implementations."""
    def process(self, data: List[str]) -> str:
        """Process input data and return result."""
        ...
```

## Documentation Standards

### Docstring Format

All modules, classes, and functions require docstrings using Google-style format:

```python
def calculate_discount(
    amount: float,
    discount_rate: float
) -> float:
    """Calculate final price after applying discount.
    
    This function applies a percentage-based discount to the provided
    amount and returns the discounted price. The discount rate must be
    between 0 and 1.
    
    Args:
        amount: The original price amount in USD
        discount_rate: Discount rate as decimal (0.0 to 1.0)
        
    Returns:
        The final price after discount application
        
    Raises:
        ValueError: If amount is negative or discount_rate is invalid
        TypeError: If arguments are not numeric types
        
    Example:
        >>> calculate_discount(100.0, 0.2)
        80.0
    """
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    if not (0 <= discount_rate <= 1):
        raise ValueError("Discount rate must be between 0 and 1")
    
    return amount * (1 - discount_rate)
```

## Common Pitfalls and Troubleshooting

### Mutable Default Arguments

**Problem**: Using mutable objects as default arguments causes unexpected behavior across function calls.

**Incorrect**:
```python
def add_to_list(item, target_list=[]):
    target_list.append(item)
    return target_list
```

**Correct**:
```python
def add_to_list(item, target_list: Optional[List] = None) -> List:
    if target_list is None:
        target_list = []
    target_list.append(item)
    return target_list
```

### String Formatting

Use f-strings for all string formatting. Avoid older `%` and `.format()` methods:

```python
# Preferred
name = "Alice"
age = 30
message = f"User {name} is {age} years old"

# Avoid
message = "User %s is %d years old" % (name, age)
message = "User {} is {} years old".format(name, age)
```

### Exception Handling

Catch specific exceptions rather than using bare `except` clauses:

```python
# Correct
try:
    result = int(user_input)
except ValueError:
    logger.error("Invalid integer input provided")
except Exception as e:
    logger.critical(f"Unexpected error: {type(e).__name__}")

# Avoid
try:
    result = int(user_input)
except:
    pass
```

## Testing Requirements

### Unit Test Standards

Every module must include unit tests with minimum 80% code coverage:

```python
# tests/test_calculator.py
import unittest
from calculator import calculate_discount

class TestCalculateDiscount(unittest.TestCase):
    """Test cases for discount calculation function."""
    
    def test_valid_discount_application(self):
        """Test discount calculation with valid inputs."""
        result = calculate_discount(100.0, 0.2)
        self.assertEqual(result, 80.0)
    
    def test_negative_amount_raises_error(self):
        """Test that negative amounts raise ValueError."""
        with self.assertRaises(ValueError):
            calculate_discount(-50.0, 0.1)
    
    def test_invalid_discount_rate_raises_error(self):
        """Test that invalid discount rates raise ValueError."""
        with self.assertRaises(ValueError):
            calculate_discount(100.0, 1.5)

if __name__ == '__main__':
    unittest.main()
```

### Running Tests and Coverage

Execute tests with coverage reporting:

```bash
# Run tests with coverage report
python -m pytest tests/ --cov=myapp --cov-report=html

# Run specific test file
python -m pytest tests/test_calculator.py -v

# Run with coverage minimum enforcement
python -m pytest tests/ --cov=myapp --cov-fail-under=80
```

## Dependency Management

### Requirements File Structure

Maintain separate requirements files for different environments:

```text
# requirements/base.txt - Core dependencies
requests==2.31.0
flask==3.0.0
sqlalchemy==2.0.23

# requirements/dev.txt - Development only
-r base.txt
pytest==7.4.3
pytest-cov==4.1.0
black==23.1.0
mypy==1.7.1
```

Install and lock dependencies using pip-tools:

```bash
# Generate locked requirements
pip-compile requirements/dev.txt --resolver=backtracking

# Install locked dependencies
pip install -r requirements/dev.txt
```

## Conclusion

Following these Python coding standards ensures enterprise-grade code quality, maintainability, and consistency across development teams. Regular reviews of this documentation and updates to align with Python ecosystem evolution are recommended annually.