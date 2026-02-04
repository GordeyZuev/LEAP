# Type Checking с ty

## Обзор

В проекте используется [ty](https://github.com/astral-sh/ty) - сверхбыстрый статический тайпчекер от Astral (создатели Ruff и uv), написанный на Rust.

### Преимущества ty

- **Скорость**: 10x-100x быстрее чем mypy и Pyright
- **Современный**: Продвинутые фичи типизации (intersection types, advanced narrowing)
- **Интеграция**: Встроен в pre-commit хуки, работает с uv
- **Постепенная типизация**: Поддержка частично типизированного кода

## Команды

### Проверка типов

```bash
# Базовая проверка всего проекта
make typecheck

# Verbose режим с подробными деталями
make typecheck-verbose

# Watch режим (автоматическая проверка при изменениях)
make typecheck-watch

# Прямой вызов ty
uv run ty check

# Проверка конкретного файла
uv run ty check api/main.py
```

### Pre-commit интеграция

ty автоматически запускается при коммите через pre-commit хуки:

```bash
# Установить хуки
make pre-commit-install

# Запустить вручную на всех файлах
make pre-commit-run
```

## Конфигурация

Настройки находятся в `pyproject.toml` в секции `[tool.ty]`:

```toml
[tool.ty.environment]
python-version = "3.14"
root = ["."]

[tool.ty.src]
include = [
    "api",
    "database",
    "models",
    # ... другие модули
]
exclude = ["alembic/versions", "tests"]
```

### Переопределения для тестов

Для тестовых файлов применяются более мягкие правила:

```toml
[[tool.ty.overrides]]
include = ["tests/**"]

[tool.ty.overrides.rules]
possibly-unresolved-reference = "warn"
```

## Подавление ошибок

### В коде

```python
# Игнорировать ошибку на конкретной строке
result = some_function()  # ty: ignore

# Или через type: ignore (также поддерживается)
result = some_function()  # type: ignore

# С кодом правила
result = some_function()  # ty: ignore[invalid-argument-type]
```

### В конфигурации

```toml
[tool.ty.rules]
# Отключить конкретное правило глобально
possibly-unresolved-reference = "ignore"

# Или сделать warning вместо error
invalid-argument-type = "warn"
```

## Интеграция с CI/CD

ty включен в команду `make quality`:

```bash
# Запускает lint + typecheck + tests-quality
make quality
```

## Типичные проблемы и решения

### 1. SQLAlchemy Column типы

**Проблема**: `current_user.id` имеет тип `Unknown | Column[str]`

**Решение**: Использовать более точные type hints в моделях:

```python
from sqlalchemy.orm import Mapped, mapped_column

class User(Base):
    id: Mapped[str] = mapped_column(String, primary_key=True)
```

### 2. Присвоение статусам

**Проблема**: Нельзя присвоить значение data descriptor атрибуту

**Решение**: Проверить что используются правильные типы и атрибуты определены корректно

### 3. Устаревшие FastAPI методы

**Проблема**: `app.on_event()` deprecated

**Решение**: Использовать `lifespan` context manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(lifespan=lifespan)
```

## Постепенное внедрение

ty поддерживает постепенную типизацию:

1. **Начните с warnings**: Установите правила в режим `"warn"` вместо `"error"`
2. **Игнорируйте legacy код**: Добавьте в exclude устаревшие модули
3. **Улучшайте постепенно**: Добавляйте типы в новый код, постепенно исправляйте старый

```toml
# Пример мягкой конфигурации
[tool.ty.rules]
invalid-argument-type = "warn"
possibly-unresolved-reference = "warn"
```

## Language Server

ty также предоставляет Language Server для IDE интеграции:

- **VS Code**: Установите расширение "ty"
- **PyCharm**: Настройте external tool
- **Neovim**: Используйте nvim-lspconfig

## Ресурсы

- [Документация ty](https://docs.astral.sh/ty/)
- [Список всех правил](https://docs.astral.sh/ty/rules/)
- [GitHub репозиторий](https://github.com/astral-sh/ty)
- [Примеры конфигурации](https://docs.astral.sh/ty/configuration/)

## Сравнение с другими тайпчекерами

| Фича                | ty          | mypy        | pyright     |
|---------------------|-------------|-------------|-------------|
| Скорость            | ⚡⚡⚡       | ⚡          | ⚡⚡        |
| Язык реализации     | Rust        | Python      | TypeScript  |
| Incremental checking| ✅          | ✅          | ✅          |
| Watch mode          | ✅          | ❌          | ✅          |
| Language Server     | ✅          | ❌          | ✅          |
| Strict mode         | ✅          | ✅          | ✅          |
| Partial typing      | ✅          | ✅          | ⚠️          |

## Roadmap интеграции

- [x] Базовая интеграция ty
- [x] Pre-commit хуки
- [x] Makefile команды
- [ ] Исправление основных ошибок типов
- [ ] Интеграция в CI/CD pipeline
- [ ] IDE Language Server настройка
- [ ] Strict mode для новых модулей
