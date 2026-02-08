# Contributing to Fiscguy

Thank you for your interest in contributing to Fiscguy! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- Virtual environment (recommended)

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/cassymyo-spec/zimra.git
cd zimra /. to change to fiscguy

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Write Code

- Follow PEP 8 style guide
- Add docstrings to functions and classes
- Include type hints where applicable
- Add inline comments for complex logic

### 3. Write Tests

All new features must include tests:

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=fiscguy

# Run specific test
pytest fiscguy/tests/test_api.py::SubmitReceiptTest::test_submit_receipt_success
```

### 4. Format Code

```bash
# Format with Black
black fiscguy

# Sort imports with isort
isort fiscguy

# Check linting
flake8 fiscguy
pylint fiscguy

# Type checking
mypy fiscguy
```

### 5. Commit Changes

```bash
git add .
git commit -m "feat: add new feature" -m "Detailed description of changes"
```

Use conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Code style (formatting, missing semicolons, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Build, dependencies, etc.

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub with:
- Clear description of changes
- Reference to any related issues
- Test results/coverage

## Code Style Guide

### Python Style

```python
# Use type hints
def submit_receipt(receipt_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit a receipt to ZIMRA.
    
    Args:
        receipt_data: Receipt dictionary
        
    Returns:
        Receipt response from ZIMRA
        
    Raises:
        ValidationError: If validation fails
        RuntimeError: If submission fails
    """
    pass

# Docstrings
class MyClass:
    """Brief description.
    
    Longer description explaining the purpose and usage.
    """
    
    def method(self):
        """Method description."""
        pass
```

### Naming Conventions

- Classes: `PascalCase` (e.g., `ZIMRAClient`)
- Functions/methods: `snake_case` (e.g., `get_status`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`)
- Private: prefix with `_` (e.g., `_internal_method`)

### Line Length

- Maximum 100 characters (Black default)
- Break long lines at logical points

## Testing Guidelines

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch
from fiscguy import open_day

class TestOpenDay:
    """Tests for open_day function."""
    
    def test_open_day_success(self):
        """Test successful fiscal day opening."""
        # Arrange
        with patch('fiscguy.api._get_device') as mock_device:
            mock_device.return_value = Mock(id=1)
            
            # Act
            result = open_day()
            
            # Assert
            assert result['fiscal_day_number'] == 1
            assert 'fiscal_day_date' in result
```

### Coverage Requirements

- Aim for >80% code coverage
- Test success paths, error cases, and edge cases
- Use mocking for external dependencies (ZIMRA API, file I/O)

## Documentation

### Update Documentation When

- Adding new functions/classes
- Changing API behavior
- Fixing bugs that require explanation
- Adding new dependencies

### Documentation Files

- `README.md` - Project overview and quick start
- `pyproject.toml` - Project metadata and dependencies
- Docstrings - Function/class documentation
- Comments - Complex logic explanation

## Common Tasks

### Adding a New API Function

1. Create function in `fiscguy/api.py`
2. Add docstring with Args, Returns, Raises
3. Add tests in `fiscguy/tests/test_api.py`
4. Update README.md with usage examples
5. Run: `pytest --cov=fiscguy`

### Adding a New Model

1. Create model in `fiscguy/models.py`
2. Create migration: `python manage.py makemigrations`
3. Create serializer in `fiscguy/serializers.py`
4. Add tests in `fiscguy/tests/`
5. Update documentation

### Fixing a Bug

1. Create test that reproduces bug (should fail)
2. Fix the bug
3. Verify test passes
4. Add comment explaining the fix if needed
5. Commit: `git commit -m "fix: description of bug fix"`

## Pull Request Process

1. **Before Submitting:**
   - Run all tests: `pytest`
   - Check coverage: `pytest --cov=fiscguy`
   - Format code: `black fiscguy && isort fiscguy`
   - Check linting: `flake8 fiscguy && pylint fiscguy`

2. **PR Description:**
   - Clear title (e.g., "Add tax validation to receipts")
   - Description of changes
   - Why these changes are needed
   - Related issues (e.g., "Closes #123")

3. **Review Process:**
   - At least one review required
   - Address feedback and update PR
   - All tests must pass
   - Coverage should not decrease

## Issues and Feature Requests

### Reporting Bugs

Include:
- Python version
- Fiscguy version
- Django version
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error traceback (if applicable)

### Feature Requests

Include:
- Use case
- Example usage
- Why it's useful
- Implementation ideas (if any)

## Questions?

- Open an issue for discussion
- Check existing issues/PRs first
- Email: fiscal@example.com

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing to Fiscguy! 
