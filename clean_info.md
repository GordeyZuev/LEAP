# Code Optimization Checklist

Quick guide for cleaning up Python modules following INSTRUCTIONS.md principles.

## 🎯 Core Principles (INSTRUCTIONS.md)

- **KISS** - Keep It Simple, Stupid
- **DRY** - Don't Repeat Yourself  
- **YAGNI** - You Aren't Gonna Need It
- **Readability** - код должен быть self-explanatory

## 🔍 What to Look For

### 1. DRY Violations (Code Duplication)

**Find:**
```python
# Same validator in multiple files
@field_validator("name", mode="before")
@classmethod
def strip_name(cls, v: str) -> str:
    if isinstance(v, str):
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
    return v
```

**Fix:** Extract to `common/validators.py` or utility module

---

### 2. Excessive Docstrings

**Bad (duplicates Field description):**
```python
class UserCreate(BaseModel):
    """Schema for creating user."""  # ❌ Obvious from class name
    
    name: str = Field(..., description="User name")
```

**Good:**
```python
class UserCreate(BaseModel):
    """Creates user with validation and password hashing."""  # ✅ Explains non-obvious behavior
    
    name: str = Field(..., description="User name")
```

**Rules (INSTRUCTIONS.md):**
- Docstrings should be **concise and useful** - not obvious facts
- Use for: complex logic, non-obvious behavior, public APIs
- Don't duplicate information from function signature
- Language: **English only**

---

### 3. Unnecessary Comments

**Bad:**
```python
# ============================================================================
# User Configuration
# ============================================================================

class UserConfig(BaseModel):
    # Privacy settings
    privacy: str = Field(...)
```

**Good:**
```python
class UserConfig(BaseModel):
    privacy: str = Field(...)
```

**Rules (INSTRUCTIONS.md):**
- Write comments **only when absolutely necessary**
- Explain "why", not "what"
- Code should be self-explanatory
- Avoid: describing obvious code, duplicating docstrings

---

### 4. Missing `model_config`

**Find:**
```python
class SomeSchema(BaseModel):
    # ❌ No model_config
    name: str
```

**Fix:**
```python
from api.schemas.common import BASE_MODEL_CONFIG

class SomeSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG  # ✅ Consistency
    
    name: str
```

---

### 5. Mixed Languages

**Bad:**
```python
description: str | None = Field(None, description="Описание пользователя")  # ❌ Russian
```

**Good:**
```python
description: str | None = Field(None, description="User description")  # ✅ English
```

---

### 6. Messy `__init__.py`

**Bad:**
```python
__all__ = [
    # ===== USERS =====
    "UserCreate",
    "UserUpdate",
    # ===== ADMIN =====
    "AdminCreate",
    ...
]
```

**Good:**
```python
__all__ = [
    "AdminCreate",
    "UserCreate",
    "UserUpdate",
]
```

---

## 🛠️ Optimization Steps

### Step 1: Find Duplicates
```bash
# Search for duplicate validators/functions
rg -A 10 "def strip_name" api/schemas/
rg -A 10 "def validate_" api/schemas/
```

### Step 2: Check Module
```bash
# Read all files in target directory
ls api/schemas/TARGET_DIR/

# Check for issues
rg "# ====" api/schemas/TARGET_DIR/
rg "\"\"\".*для.*\"\"\"" api/schemas/TARGET_DIR/  # Russian docstrings
```

### Step 3: Optimize
1. Extract duplicate code to `common/validators.py` or `common/utils.py`
2. Remove excessive docstrings
3. Remove comment separators
4. Add missing `model_config = BASE_MODEL_CONFIG`
5. Translate Russian → English
6. Clean up `__init__.py`

### Step 4: Verify
```bash
# Run linter
uv run ruff check api/schemas/TARGET_DIR/

# Test imports
uv run python -c "from api.schemas.TARGET_DIR import *; print('✓ OK')"
```

---

## 📋 Quick Checklist

Before/After optimization:

- [ ] No duplicate validators/functions
- [ ] Docstrings explain non-obvious behavior only
- [ ] No excessive comment separators (`# ====`)
- [ ] All schemas have `model_config`
- [ ] All descriptions in English
- [ ] `__init__.py` clean and sorted
- [ ] `ruff check` passes
- [ ] Imports work correctly

---

## 📊 Expected Results

- **-100 to -200 lines** (depending on module size)
- **No functional changes**
- **Better readability**
- **Consistent code style**


---

## ⚠️ Don't Touch

- **Logic/business rules** - only clean up style
- **Type hints** - keep all Pydantic types
- **Validation** - keep all validators, just deduplicate
- **Tests** - optimization is style-only, tests stay same
