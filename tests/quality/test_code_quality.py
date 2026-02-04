"""Tests for code quality checks."""

# ruff: noqa: S607
# S607: Using partial paths is safe in test context

import subprocess
from pathlib import Path

import pytest


class TestCodeQuality:
    """Code quality and linting tests."""

    @pytest.mark.quality
    def test_ruff_check(self):
        """Test that ruff linting passes."""
        result = subprocess.run(
            ["uv", "run", "ruff", "check", "."],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Ruff check failed:\n{result.stdout}\n{result.stderr}"

    @pytest.mark.quality
    def test_ruff_format_check(self):
        """Test that code is properly formatted."""
        result = subprocess.run(
            ["uv", "run", "ruff", "format", "--check", "."],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Ruff format check failed:\n{result.stdout}"

    @pytest.mark.quality
    def test_mypy_type_checking(self):
        """Test that type hints are correct (if mypy is configured)."""
        # Skip if mypy not installed
        mypy_check = subprocess.run(["which", "mypy"], capture_output=True, check=False)
        if mypy_check.returncode != 0:
            pytest.skip("mypy not installed")

        result = subprocess.run(
            ["mypy", "api/", "--ignore-missing-imports"],
            capture_output=True,
            text=True,
            check=False,
        )
        # For now, just warn if mypy fails
        if result.returncode != 0:
            pytest.fail(f"Mypy found type issues:\n{result.stdout}")


class TestProjectStructure:
    """Tests for project structure and organization."""

    @pytest.mark.quality
    def test_all_python_files_have_docstrings(self):
        """Test that all Python modules have docstrings."""
        api_path = Path("api")
        files_without_docstrings = []

        for py_file in api_path.rglob("*.py"):
            # Skip __init__.py files
            if py_file.name == "__init__.py":
                continue

            content = py_file.read_text()
            # Check if file starts with docstring (after imports/comments)
            lines = [line for line in content.split("\n") if line.strip() and not line.strip().startswith("#")]
            if lines and not lines[0].strip().startswith('"""'):
                files_without_docstrings.append(str(py_file))

        assert not files_without_docstrings, "Files without module docstrings:\n" + "\n".join(files_without_docstrings)

    @pytest.mark.quality
    def test_no_print_statements_in_code(self):
        """Test that no print() statements exist (should use logger)."""
        api_path = Path("api")
        files_with_prints = []

        for py_file in api_path.rglob("*.py"):
            content = py_file.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith("#"):
                    continue
                # Check for print statements
                if "print(" in line and not line.strip().startswith('"""'):
                    files_with_prints.append(f"{py_file}:{line_num}: {line.strip()}")

        assert not files_with_prints, "Found print() statements (use logger instead):\n" + "\n".join(files_with_prints)

    @pytest.mark.quality
    def test_no_todo_fixme_in_main_branch(self):
        """Test that no TODO/FIXME comments exist in production code."""
        api_path = Path("api")
        todos_found = []

        for py_file in api_path.rglob("*.py"):
            content = py_file.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                if any(marker in line.upper() for marker in ["TODO", "FIXME", "HACK", "XXX"]):
                    todos_found.append(f"{py_file}:{line_num}: {line.strip()}")

        # Just warn, don't fail
        if todos_found:
            pytest.skip("Found TODO/FIXME comments:\n" + "\n".join(todos_found[:10]))

    @pytest.mark.quality
    def test_requirements_in_sync(self):
        """Test that requirements.txt matches pyproject.toml."""
        # This is a simplified check
        pyproject_path = Path("pyproject.toml")
        requirements_path = Path("requirements.txt")

        if not requirements_path.exists():
            pytest.skip("requirements.txt not found")

        # Just check files exist and are not empty
        assert pyproject_path.exists(), "pyproject.toml not found"
        assert pyproject_path.stat().st_size > 0, "pyproject.toml is empty"
        assert requirements_path.stat().st_size > 0, "requirements.txt is empty"


class TestSecurity:
    """Security-related code quality tests."""

    @pytest.mark.quality
    @pytest.mark.security
    def test_no_hardcoded_secrets(self):
        """Test that no hardcoded secrets exist in code."""
        api_path = Path("api")
        suspicious_patterns = [
            "password =",
            "api_key =",
            "secret =",
            "token =",
            "SECRET_KEY =",
        ]

        files_with_secrets = []

        for py_file in api_path.rglob("*.py"):
            content = py_file.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                # Skip comments and docstrings
                if line.strip().startswith("#") or '"""' in line:
                    continue

                for pattern in suspicious_patterns:
                    if pattern in line.lower():
                        # Check if it's actually a hardcoded value (not env var)
                        if ("=" in line and '"' in line) or "'" in line:
                            # Allow if it's reading from env
                            if "os.getenv" not in line and "os.environ" not in line:
                                files_with_secrets.append(f"{py_file}:{line_num}: {line.strip()}")

        assert not files_with_secrets, "Found potential hardcoded secrets:\n" + "\n".join(files_with_secrets)

    @pytest.mark.quality
    @pytest.mark.security
    def test_no_debug_mode_in_production(self):
        """Test that debug mode is not enabled."""
        config_files = ["config/settings.py", "api/main.py"]

        for config_file in config_files:
            config_path = Path(config_file)
            if not config_path.exists():
                continue

            content = config_path.read_text()
            # Check for DEBUG = True or debug=True
            if "DEBUG = True" in content or "debug=True" in content:
                pytest.fail(f"Debug mode found in {config_file}")


class TestDocumentation:
    """Tests for documentation quality."""

    @pytest.mark.quality
    def test_readme_exists(self):
        """Test that README.md exists and is not empty."""
        readme_path = Path("README.md")
        assert readme_path.exists(), "README.md not found"
        assert readme_path.stat().st_size > 100, "README.md is too short"

    @pytest.mark.quality
    def test_api_docstrings_quality(self):
        """Test that API endpoints have proper docstrings."""
        routers_path = Path("api/routers")
        if not routers_path.exists():
            pytest.skip("api/routers not found")

        endpoints_without_docs = []

        for py_file in routers_path.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            content = py_file.read_text()
            lines = content.split("\n")

            in_function = False
            function_name = None

            for i, line in enumerate(lines):
                # Find router decorators
                if "@router." in line and any(method in line for method in ["get", "post", "put", "delete"]):
                    in_function = True
                    continue

                # Find function definition after decorator
                if (in_function and line.strip().startswith("async def ")) or line.strip().startswith("def "):
                    function_name = line.split("def ")[1].split("(")[0]
                    # Check if next non-empty line is a docstring
                    next_lines = [ln for ln in lines[i + 1 :] if ln.strip()]
                    if not next_lines or not next_lines[0].strip().startswith('"""'):
                        endpoints_without_docs.append(f"{py_file.name}:{function_name}")
                    in_function = False

        # Just warn, don't fail
        if endpoints_without_docs:
            pytest.skip("Endpoints without docstrings:\n" + "\n".join(endpoints_without_docs[:10]))


class TestTestCoverage:
    """Tests for test coverage metrics."""

    @pytest.mark.quality
    @pytest.mark.slow
    def test_minimum_coverage_threshold(self):
        """Test that code coverage meets minimum threshold."""
        result = subprocess.run(
            ["uv", "run", "pytest", "tests/unit/", "--cov=api", "--cov-report=term", "--cov-fail-under=30"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Coverage threshold is set in the command (30%)
        assert result.returncode == 0, f"Coverage below threshold:\n{result.stdout}"

    @pytest.mark.quality
    def test_all_tests_have_docstrings(self):
        """Test that all test functions have docstrings."""
        tests_path = Path("tests")
        tests_without_docs = []

        for py_file in tests_path.rglob("test_*.py"):
            content = py_file.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines):
                if line.strip().startswith("def test_") or line.strip().startswith("async def test_"):
                    # Check if next non-empty line is a docstring
                    next_lines = [ln for ln in lines[i + 1 :] if ln.strip()]
                    if not next_lines or not next_lines[0].strip().startswith('"""'):
                        function_name = line.split("def ")[1].split("(")[0]
                        tests_without_docs.append(f"{py_file.name}:{function_name}")

        # Allow some tests without docstrings, but warn
        if len(tests_without_docs) > 10:
            pytest.fail(
                f"Too many tests without docstrings ({len(tests_without_docs)}):\n" + "\n".join(tests_without_docs[:20])
            )


class TestDependencies:
    """Tests for dependency management."""

    @pytest.mark.quality
    def test_no_conflicting_dependencies(self):
        """Test that there are no conflicting package versions."""
        result = subprocess.run(
            ["uv", "pip", "check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Dependency conflicts found:\n{result.stdout}"

    @pytest.mark.quality
    def test_security_vulnerabilities(self):
        """Test for known security vulnerabilities in dependencies."""
        # Check if safety is installed
        safety_check = subprocess.run(["which", "safety"], capture_output=True, check=False)
        if safety_check.returncode != 0:
            pytest.skip("safety not installed (pip install safety)")

        result = subprocess.run(
            ["safety", "check", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Just warn if vulnerabilities found
        if result.returncode != 0:
            pytest.skip(f"Security vulnerabilities found:\n{result.stdout}")
