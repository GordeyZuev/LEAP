# Testing Roadmap - Пошаговый план

## Текущий статус: Phase 1 (Unit Tests) - 30% complete

✅ **Done:** 44 unit tests для GET endpoints (31% coverage)

## Phase 1: Unit Tests расширение

### Week 1-2: POST/PUT/DELETE endpoints

#### Recordings API

**test_recordings_post.py** (15 тестов)
```python
# POST /api/v1/recordings
- test_create_recording_success
- test_create_recording_without_auth_returns_401
- test_create_recording_with_invalid_data_returns_422
- test_create_recording_exceeds_quota_returns_403
- test_create_recording_duplicate_returns_409

# PUT /api/v1/recordings/{id}
- test_update_recording_success
- test_update_recording_not_found_returns_404
- test_update_recording_not_owner_returns_403
- test_update_recording_partial_update

# DELETE /api/v1/recordings/{id}
- test_delete_recording_soft_delete
- test_delete_recording_hard_delete
- test_delete_recording_not_found
- test_delete_recording_not_owner

# POST /api/v1/recordings/{id}/process
- test_trigger_processing
- test_trigger_processing_with_config_override
```

#### Templates API

**test_templates_post.py** (12 тестов)
```python
# POST /api/v1/templates
- test_create_template_success
- test_create_template_as_draft
- test_create_template_with_matching_rules

# PUT /api/v1/templates/{id}
- test_update_template_success
- test_update_template_activate
- test_update_template_not_owner

# DELETE /api/v1/templates/{id}
- test_delete_template_success
- test_delete_template_with_recordings

# POST /api/v1/templates/{id}/test
- test_test_template_matching
- test_test_template_with_sample_data

# POST /api/v1/templates/{id}/apply
- test_apply_template_to_recording
- test_apply_template_validation
```

#### Credentials API

**test_credentials_post.py** (10 тестов)
```python
# POST /api/v1/credentials
- test_add_youtube_credentials
- test_add_vk_credentials
- test_add_zoom_credentials
- test_add_invalid_credentials

# PUT /api/v1/credentials/{id}
- test_update_credentials
- test_update_credentials_validation

# DELETE /api/v1/credentials/{id}
- test_delete_credentials
- test_delete_credentials_in_use

# POST /api/v1/credentials/{id}/test
- test_test_youtube_connection
- test_test_vk_connection
```

**Команды:**
```bash
# Создать файлы
touch tests/unit/api/test_recordings_post.py
touch tests/unit/api/test_templates_post.py
touch tests/unit/api/test_credentials_post.py

# Запустить
uv run pytest tests/unit/api/test_*_post.py -v
```

**Цель:** +37 тестов, coverage 40%

### Week 3: Services Layer

#### QuotaService

**test_quota_service.py** (15 тестов)
```python
class TestQuotaService:
    # Quota checking
    - test_check_can_create_recording
    - test_check_quota_exceeded
    - test_check_with_overage_enabled

    # Usage tracking
    - test_increment_recordings_count
    - test_increment_storage_usage
    - test_decrement_on_delete

    # Reset logic
    - test_quota_reset_monthly
    - test_quota_history_tracking

    # Limits enforcement
    - test_concurrent_tasks_limit
    - test_storage_limit_enforcement
    - test_automation_jobs_limit

    # Overage
    - test_calculate_overage_cost
    - test_overage_limit_check
    - test_overage_notifications
    - test_overage_auto_disable
```

#### TemplateMatcherService

**test_template_matcher.py** (10 тестов)
```python
class TestTemplateMatcher:
    # Matching logic
    - test_match_by_display_name_pattern
    - test_match_by_duration_range
    - test_match_by_start_time
    - test_match_multiple_rules

    # Priority
    - test_highest_priority_template_selected
    - test_no_match_returns_none

    # Complex scenarios
    - test_regex_pattern_matching
    - test_case_insensitive_matching
    - test_multiple_templates_matching
    - test_draft_templates_excluded
```

#### ConfigService

**test_config_service.py** (8 тестов)
```python
class TestConfigService:
    - test_resolve_config_hierarchy
    - test_user_config_overrides_global
    - test_template_config_overrides_user
    - test_runtime_config_overrides_all
    - test_merge_configs
    - test_validate_config_schema
    - test_get_effective_config
    - test_config_caching
```

**Цель:** +33 теста, coverage 50%

### Week 4: Repositories & Utils

#### Repositories

**test_recording_repos.py** (12 тестов)
```python
class TestRecordingRepository:
    # CRUD
    - test_create_recording
    - test_get_by_id
    - test_list_by_user
    - test_update_recording
    - test_delete_recording

    # Queries
    - test_filter_by_status
    - test_filter_by_template
    - test_search_by_name
    - test_pagination

    # Complex
    - test_get_with_relations
    - test_bulk_update_status
    - test_count_by_status
```

#### Utils

**test_date_utils.py** (8 тестов)
**test_formatting.py** (6 тестов)
**test_data_processing.py** (5 тестов)

**Цель:** +31 тест, coverage 60%

## Phase 2: Integration Tests

### Week 5-6: Setup & Infrastructure

#### 1. Docker Setup

**docker-compose.test.yml**
```yaml
version: '3.8'

services:
  postgres-test:
    image: postgres:15
    environment:
      POSTGRES_DB: leap_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data  # Fast in-memory DB

  redis-test:
    image: redis:7-alpine
    ports:
      - "6380:6379"
```

#### 2. Test Database Fixtures

**tests/integration/conftest.py**
```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    """Database engine for tests."""
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@localhost:5433/leap_test",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    """Isolated database session per test."""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

@pytest.fixture
async def test_user(db_session):
    """Create test user in DB."""
    user = UserModel(
        id="test_user_123",
        email="test@example.com",
        hashed_password="hashed",
        role="user"
    )
    db_session.add(user)
    await db_session.commit()
    return user
```

#### 3. Integration Test Client

```python
@pytest.fixture
async def integration_client(db_session):
    """FastAPI test client with real DB."""
    # Override get_db_session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
```

**Команды:**
```bash
# Setup
make tests-integration-setup

# Run
make tests-integration
```

### Week 7-8: API Integration Tests

**tests/integration/test_api_recordings.py** (20 тестов)
```python
@pytest.mark.integration
class TestRecordingsIntegration:
    async def test_create_and_retrieve_recording(self, integration_client, test_user):
        """Full CRUD cycle with real DB."""
        # Create
        response = await integration_client.post(
            "/api/v1/recordings",
            json={
                "display_name": "Integration Test",
                "duration": 3600,
                "start_time": "2026-01-01T00:00:00Z"
            },
            headers={"Authorization": f"Bearer {test_user.token}"}
        )
        assert response.status_code == 201
        recording_id = response.json()["id"]

        # Retrieve
        response = await integration_client.get(
            f"/api/v1/recordings/{recording_id}",
            headers={"Authorization": f"Bearer {test_user.token}"}
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Integration Test"

    async def test_multi_tenancy_enforcement(
        self, integration_client, test_user, other_user
    ):
        """Verify users cannot access each other's recordings."""
        # User1 creates recording
        response = await integration_client.post(
            "/api/v1/recordings",
            json={"display_name": "User1 Recording", ...},
            headers={"Authorization": f"Bearer {test_user.token}"}
        )
        recording_id = response.json()["id"]

        # User2 tries to access
        response = await integration_client.get(
            f"/api/v1/recordings/{recording_id}",
            headers={"Authorization": f"Bearer {other_user.token}"}
        )
        assert response.status_code == 404  # Not found (not 403!)

    async def test_cascade_delete_recording(self, integration_client, test_user):
        """Test that deleting recording cascades to related data."""
        # Create recording with outputs
        recording_id = await create_test_recording_with_outputs()

        # Delete
        response = await integration_client.delete(
            f"/api/v1/recordings/{recording_id}",
            headers={"Authorization": f"Bearer {test_user.token}"}
        )
        assert response.status_code == 204

        # Verify outputs also deleted
        outputs = await db_session.execute(
            select(OutputTarget).where(OutputTarget.recording_id == recording_id)
        )
        assert len(outputs.all()) == 0
```

**Цель:** +60 тестов integration, coverage 45%

### Week 9: Celery Tasks Integration

**tests/integration/test_celery_tasks.py** (15 тестов)
```python
@pytest.mark.integration
class TestCeleryTasks:
    async def test_download_task_execution(self, db_session, celery_worker):
        """Test real download task with mocked external API."""
        # Setup
        recording = await create_test_recording()

        # Mock Zoom API
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                "https://api.zoom.us/v2/meetings/123/recordings",
                json={"download_url": "https://zoom.us/rec/download/123"},
                status=200,
            )

            # Execute task
            result = download_recording_task.apply_async(
                args=[recording.id]
            ).get(timeout=30)

            assert result["status"] == "success"

            # Verify DB state
            await db_session.refresh(recording)
            assert recording.status == ProcessingStatus.DOWNLOADED
            assert recording.local_video_path is not None

    async def test_task_retry_on_failure(self, db_session):
        """Test task retry logic."""
        recording = await create_test_recording()

        # First attempt fails
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                "https://api.zoom.us/...",
                status=500,
            )

            with pytest.raises(Retry):
                download_recording_task(recording.id)

            # Verify retry count incremented
            await db_session.refresh(recording)
            assert recording.retry_count == 1
```

**Цель:** +15 тестов, coverage 48%

## Phase 3: E2E Tests

### Week 10-11: Critical Flows

**tests/e2e/test_recording_pipeline.py** (5 тестов)
```python
@pytest.mark.e2e
class TestRecordingPipeline:
    async def test_complete_processing_pipeline(
        self,
        e2e_system,  # Full Docker Compose stack
        zoom_api_mock,
        youtube_api_mock
    ):
        """Test: Sync → Download → Process → Upload."""
        # 1. Sync from Zoom
        recording = await sync_zoom_recording("meeting_123")
        assert recording.status == ProcessingStatus.INITIALIZED

        # 2. Wait for download (async worker)
        await wait_for_status(recording.id, ProcessingStatus.DOWNLOADED, timeout=60)

        # 3. Wait for processing
        await wait_for_status(recording.id, ProcessingStatus.PROCESSED, timeout=300)

        # 4. Upload to YouTube
        await trigger_upload(recording.id, platform="youtube")
        await wait_for_status(recording.id, ProcessingStatus.UPLOADED, timeout=120)

        # Verify final state
        recording = await get_recording(recording.id)
        assert recording.status == ProcessingStatus.UPLOADED
        assert len(recording.outputs) == 1
        assert recording.outputs[0].target_type == "youtube"
        assert recording.outputs[0].status == TargetStatus.UPLOADED
```

**tests/e2e/test_automation.py** (4 теста)
```python
@pytest.mark.e2e
async def test_template_automation_flow():
    """Test automatic template matching and processing."""
    # 1. Create template with matching rules
    template = await create_template({
        "name": "Auto Python Lectures",
        "matching_rules": {
            "display_name_pattern": ".*Python.*",
            "min_duration": 1800
        },
        "processing_config": {"trimming": {"enabled": True}},
        "output_config": {"auto_upload": True, "preset_ids": [1]}
    })

    # 2. Sync recording that matches
    recording = await sync_zoom_recording(
        display_name="Python Advanced Course",
        duration=3600
    )

    # 3. Wait for template matching
    await asyncio.sleep(5)
    await db_session.refresh(recording)
    assert recording.template_id == template.id

    # 4. Wait for auto-processing
    await wait_for_status(recording.id, ProcessingStatus.PROCESSED)

    # 5. Verify auto-upload triggered
    await wait_for_status(recording.id, ProcessingStatus.UPLOADED)
```

**Цель:** +10 тестов E2E, coverage 50%

## Phase 4: Специализированные тесты

### Week 12: Performance & Load Testing

**tests/performance/test_api_benchmarks.py**
```python
def test_list_recordings_performance(benchmark, setup_1000_recordings):
    """Benchmark listing 1000 recordings."""
    def list_operation():
        return client.get("/api/v1/recordings?per_page=100")

    result = benchmark(list_operation)
    assert result.stats.mean < 0.5  # < 500ms
```

**tests/performance/locustfile.py**
```python
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def list_recordings(self):
        self.client.get("/api/v1/recordings")

    @task(2)
    def get_recording(self):
        self.client.get(f"/api/v1/recordings/{self.recording_id}")

    @task(1)
    def create_recording(self):
        self.client.post("/api/v1/recordings", json={...})
```

**Run:**
```bash
# Benchmark
uv run pytest tests/performance/ -v

# Load test
locust -f tests/performance/locustfile.py --host=http://localhost:8000
```

## Makefile Commands

Обновить Makefile:

```makefile
# Testing commands
.PHONY: tests-all tests-mock tests-integration tests-e2e tests-performance

# Unit tests (fast)
tests-mock:
	@echo "🧪 Running unit tests with mocks..."
	@uv run ruff check tests/
	@uv run pytest tests/unit/ -v --tb=short

# Integration tests (with DB)
tests-integration:
	@echo "🔗 Running integration tests..."
	@docker-compose -f docker-compose.test.yml up -d
	@sleep 3
	@uv run pytest tests/integration/ -v --tb=short
	@docker-compose -f docker-compose.test.yml down

# E2E tests (full stack)
tests-e2e:
	@echo "🌐 Running E2E tests..."
	@docker-compose -f docker-compose.test.yml up -d
	@uv run pytest tests/e2e/ -v --tb=short
	@docker-compose -f docker-compose.test.yml down

# Performance tests
tests-performance:
	@echo "⚡ Running performance tests..."
	@uv run pytest tests/performance/ -v

# All tests
tests-all: tests-mock tests-integration tests-e2e
	@echo "✅ All tests completed!"

# Coverage report
tests-coverage:
	@uv run pytest tests/ --cov=api --cov-report=html --cov-report=term
	@echo "📊 Coverage report: htmlcov/index.html"

# Watch mode (for TDD)
tests-watch:
	@uv run ptw -- -v --tb=short
```

## CI/CD Integration

**.github/workflows/tests.yml**
```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.14'
      - run: pip install uv
      - run: uv sync
      - run: uv run ruff check .

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install uv
      - run: uv sync
      - run: make tests-mock

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: leap_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: make tests-integration

  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: make tests-coverage
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

## Success Metrics

### Phase 1 Complete
- ✅ 150+ unit tests
- ✅ 60% code coverage
- ✅ All tests < 2s

### Phase 2 Complete
- ✅ 80+ integration tests
- ✅ 50% code coverage
- ✅ All integration tests < 30s

### Phase 3 Complete
- ✅ 15+ E2E tests
- ✅ Critical flows covered
- ✅ E2E tests < 5min

### Phase 4 Complete
- ✅ Performance baselines established
- ✅ Load testing infrastructure
- ✅ 70%+ total coverage

## Resources Needed

### Time
- **Phase 1:** 4 weeks (unit tests expansion)
- **Phase 2:** 3 weeks (integration tests)
- **Phase 3:** 2 weeks (E2E tests)
- **Phase 4:** 1 week (performance)
- **Total:** ~10 weeks

### Infrastructure
- PostgreSQL test database
- Redis test instance
- Docker Compose
- CI/CD runners

### Skills
- pytest advanced features
- async/await testing
- Docker/containers
- Load testing
- Test automation

## Next Actions

1. **Сейчас:**
   ```bash
   # Создать структуру для Phase 1
   mkdir -p tests/unit/api/post
   mkdir -p tests/unit/services
   mkdir -p tests/unit/repositories

   # Создать первые тесты
   touch tests/unit/api/test_recordings_post.py
   ```

2. **Эта неделя:**
   - Написать 15 тестов для POST /recordings
   - Написать 12 тестов для POST /templates

3. **Следующая неделя:**
   - Setup integration test infrastructure
   - Написать первые integration тесты

Начать с самого важного: **POST/PUT/DELETE для recordings** - это критичная функциональность!
