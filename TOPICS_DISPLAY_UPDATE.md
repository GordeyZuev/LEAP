# Topics Display Configuration Update

**Date:** 2026-01-23

## Summary

Обновлены дефолтные значения для `topics_display` конфигурации, чтобы по умолчанию показывать ВСЕ топики без фильтрации.

## Changes

### Before (old defaults):
```json
{
  "topics_display": {
    "max_count": 10,      // показывать только 10 топиков
    "min_length": 5,      // фильтровать короткие топики
    "max_length": 100     // фильтровать длинные топики
  }
}
```

### After (new defaults):
```json
{
  "topics_display": {
    "max_count": 999,     // показывать все топики (практически без лимита)
    "min_length": 0,      // не фильтровать короткие топики
    "max_length": 999     // не фильтровать длинные топики
  }
}
```

## Rationale

1. **AI-generated topics** уже имеют хорошее качество - не нужна дополнительная фильтрация
2. **Явное поведение** - пользователь видит все сгенерированные топики
3. **Гибкость** - можно легко ограничить, установив нужное значение в preset/template

## Usage Examples

### Show all topics (default):
```json
{
  "topics_display": {
    "max_count": 999  // или можно не указывать - будет default
  }
}
```

### Limit to 10 topics:
```json
{
  "topics_display": {
    "max_count": 10
  }
}
```

### Filter short topics:
```json
{
  "topics_display": {
    "min_length": 20  // показывать только топики длиннее 20 символов
  }
}
```

### Platform-specific limits:
```json
{
  "vk": {
    "topics_display": {
      "max_count": 999  // все топики для VK
    }
  },
  "youtube": {
    "topics_display": {
      "max_count": 10   // ограничить для YouTube
    }
  }
}
```

## Files Updated

### Code:
- `api/schemas/config/user_config.py` - TopicsDisplayConfig defaults
- `config/settings.py` - DEFAULT_USER_CONFIG
- `api/helpers/template_renderer.py` - rendering logic and defaults
- `api/schemas/template/preset_metadata.py` - validation limits

### Documentation:
- `docs/TEMPLATES_PRESETS_SOURCES_GUIDE.md`
- `docs/TEMPLATES.md`
- `docs/DATABASE_DESIGN.md`
- `docs/examples/preset_metadata_examples.json`
- `docs/examples/vk_preset_example.json`

## Migration

**Existing configurations** will continue to work without changes:
- If you had `max_count: 10` explicitly set → it will remain 10
- If you had `max_count: null` → it will now use new default (999)
- User configs created before this update → keep old values until manually updated

**No database migration needed** - это изменение только default значений в коде.

## Behavior

### Config Resolution Priority (от низшего к высшему):
1. **user_config** (base defaults - now 999)
2. **preset.preset_metadata**
3. **template.metadata_config** (platform-specific overrides supported)
4. **recording.processing_preferences.metadata_config** (highest)

### How `null` Works in Merging:

**`null` = "don't override, use value from lower level"**

**Example 1:**
```json
user_config:  max_count = 999
preset:       max_count = 10
template:     max_count = null

Result: 10 (from preset, template null is skipped)
```

**Example 2:**
```json
user_config:  max_count = 999
preset:       max_count = null
template:     (not specified)

Result: 999 (from user_config, preset null is skipped)
```

**Example 3:**
```json
user_config:  max_count = 999
preset:       max_count = null
template:     max_count = null

Result: 999 (both nulls are skipped, user_config is used)
```

### Special Values:
- `max_count = 999` - показать практически все топики (default)
- `max_count = 10` - показать 10 топиков
- `max_count = 0` - показать все (не применять фильтр)
- `max_count = null` - не перезаписывать, использовать значение из нижележащего уровня
- `min_length = 0` - не фильтровать короткие топики (default)
- `max_length = 999` - не фильтровать длинные топики (default)

## Testing

Протестировано на записи с id=1 (3D-зрение):
- **VK:** 50 топиков → работает корректно с `max_count: null` (используется default)
- **YouTube:** 10 топиков → работает с явным `max_count: 10` в preset
