# Testing Infrastructure для LEAP

## 🚀 Quick Start

```bash
# Run tests
make tests-mock

# Check code quality
make quality

# Install pre-commit hooks (recommended)
make pre-commit-install
```

## 📊 Current Status

```
✅ 44 unit tests passing (5 skipped)
✅ 31% code coverage
✅ 0 linter errors
⚡ ~20s execution time
```

## 📁 Structure

```
tests/
├── README.md                    # This file
├── ROADMAP.md                   # Detailed implementation plan
├── pytest.ini                   # Pytest configuration
├── conftest.py                  # Shared fixtures
│
├── fixtures/
│   └── factories.py            # Test data factories
│
├── unit/                        # Unit tests (44 tests)
│   └── api/
│       ├── test_recordings_get.py    (8 tests)
│       ├── test_templates_get.py     (6 tests)
│       ├── test_users_get.py         (8 tests)
│       └── test_credentials_get.py   (10 tests)
│
└── quality/                     # Code quality tests (15 checks)
    └── test_code_quality.py
```

## 🛠️ Commands

### Testing

```bash
make tests-mock        # Unit tests (fast, ~20s)
make tests-quality     # Quality checks
make tests-security    # Security tests
make quality           # lint + quality tests
```

### Linting

```bash
make lint              # Check code
make lint-fix          # Auto-fix + format
make format            # Format only
```

### Pre-commit

```bash
make pre-commit-install  # Install hooks (once)
make pre-commit-run      # Run manually
```

## 📈 Coverage

**Current: 31%**

| Component | Coverage |
|-----------|----------|
| recordings.py | 17% |
| templates.py | 29% |
| users.py | 38% |
| credentials.py | 41% |

**Target: 70%** (see [ROADMAP.md](ROADMAP.md))

## 🎯 Test Types

### ✅ Unit Tests (Current)
Fast, isolated tests with mocks.

**Covered:**
- GET /recordings (8 tests)
- GET /templates (6 tests)
- GET /users/me (8 tests)
- GET /credentials (10 tests)

**Run:** `make tests-mock`

### ⏳ Integration Tests (Planned)
Tests with real database.

**Target:** +80 tests, +15% coverage
**Command:** `make tests-integration` (not yet)

### ⏳ E2E Tests (Planned)
Full system tests.

**Target:** +15 tests, critical flows
**Command:** `make tests-e2e` (not yet)

## 🧪 Writing Tests

### Example: Unit Test

```python
@pytest.mark.unit
def test_list_recordings(client, mocker, mock_user):
    """Test successful retrieval of recordings list."""
    # Arrange
    mock_recordings = [
        create_mock_recording(record_id=1, user_id=mock_user.id),
        create_mock_recording(record_id=2, user_id=mock_user.id),
    ]

    mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
    mock_repo_instance = MagicMock()
    mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
    mock_repo.return_value = mock_repo_instance

    # Act
    response = client.get("/api/v1/recordings")

    # Assert
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
```

### Fixtures Available

- `mock_user` - test user
- `mock_admin_user` - admin user
- `mock_db_session` - mock DB session
- `client` - TestClient with mocked dependencies
- `admin_client` - TestClient with admin

### Factory Functions

```python
from tests.fixtures.factories import (
    create_mock_recording,
    create_mock_template,
    create_mock_credential,
)

# Usage
recording = create_mock_recording(
    record_id=1,
    display_name="Test",
    user_id="user_123"
)
```

## 🔍 Code Quality

### Automated Checks ✅

- ✅ Ruff linting & formatting
- ✅ No print() statements (use logger)
- ✅ No hardcoded secrets
- ✅ Module docstrings (English)
- ✅ Type hints
- ✅ Multi-tenancy enforcement

### Pre-commit Hooks

**Installed?** `make pre-commit-install`

**Runs automatically on commit:**
- Ruff check + format
- YAML/JSON validation
- Security checks (bandit)
- Trailing whitespace
- Large files detection
- Private keys detection

## 📋 Useful Commands

### Run specific tests

```bash
# One test file
uv run pytest tests/unit/api/test_recordings_get.py -v

# One test
uv run pytest tests/unit/api/test_recordings_get.py::test_list_recordings_success -v

# Failed tests only
uv run pytest --lf

# Parallel (faster)
uv run pytest -n auto

# With debugger
uv run pytest --pdb
```

### Coverage reports

```bash
# HTML report
uv run pytest tests/unit/ --cov=api --cov-report=html
open htmlcov/index.html

# Terminal report
uv run pytest tests/unit/ --cov=api --cov-report=term-missing
```

### Markers

```bash
# Only unit tests
uv run pytest -m unit

# Exclude slow tests
uv run pytest -m "not slow"

# Quality checks only
uv run pytest -m quality
```

## 🎓 Best Practices

### Code Style

- ✅ Docstrings in English, concise
- ✅ Comments explain "why", not "what"
- ✅ Type hints where beneficial
- ✅ KISS principle
- ✅ Use logger instead of print()

### Test Writing

- ✅ AAA pattern (Arrange-Act-Assert)
- ✅ One test = one scenario
- ✅ Descriptive names
- ✅ Test multi-tenancy
- ✅ Mock external dependencies

### Before Commit

```bash
make lint-fix      # Fix code issues
make tests-mock    # Run tests
git commit         # Pre-commit runs automatically
```

## 📈 Next Steps

See **[ROADMAP.md](ROADMAP.md)** for detailed plan:

1. **Week 1-2:** POST/PUT/DELETE endpoints (+37 tests, 40% coverage)
2. **Week 3:** Services layer (+33 tests, 50% coverage)
3. **Week 4:** Repositories & Utils (+31 tests, 60% coverage)
4. **Week 5-9:** Integration tests (+80 tests)
5. **Week 10-11:** E2E tests (+15 tests)

**Goal:** 200+ tests, 70% coverage

## 🐛 Troubleshooting

### Tests fail with "module not found"

```bash
uv sync  # Install dependencies
```

### Pre-commit is slow

First run is slow (installs environments). Subsequent runs are fast.

### Coverage report

```bash
uv run pytest --cov=api --cov-report=html
open htmlcov/index.html
```

## 📚 Resources

- **[ROADMAP.md](ROADMAP.md)** - Complete implementation plan with examples
- **[pytest docs](https://docs.pytest.org/)** - Official pytest documentation
- **[FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)** - FastAPI testing guide
- **[docs/INDEX.md](../docs/INDEX.md)** - Documentation index (guides, technical reference, changelog)

---

**Created:** 2026-02-04
**Status:** ✅ Phase 1 Complete (Unit Tests)
**Next:** Phase 2 (Integration Tests)
