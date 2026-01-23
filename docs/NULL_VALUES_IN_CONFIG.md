# NULL Values in Configuration Hierarchy

## TL;DR

**`null` в конфигурации = "не перезаписывать, использовать значение из нижележащего уровня"**

## Configuration Hierarchy (от низшего к высшему)

```
1. user_config (base defaults)
   ↓
2. preset.preset_metadata (platform defaults)
   ↓
3. template.metadata_config (content-specific + platform-specific)
   ↓
4. recording.processing_preferences (manual override - highest)
```

## How Merging Works

### Code (from `config_resolver.py`):

```python
def _merge_configs(self, base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    
    for key, value in override.items():
        # Skip None values - they don't override base
        if value is None:
            continue  # ← Ключевая логика!
        
        if isinstance(value, dict):
            result[key] = self._merge_configs(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    
    return result
```

**Поведение:**
- Если `value is None` → **пропускаем** (не перезаписываем)
- Если `value = 10` → **перезаписываем**
- Если ключ отсутствует → **не трогаем базовое значение**

## Examples

### Example 1: Template overrides preset

```json
// Config levels:
user_config:  { "max_count": 999 }
preset:       { "max_count": 10 }
template:     { "max_count": 5 }

// Merging:
1. base = { "max_count": 999 }
2. merge preset: { "max_count": 10 } → result = { "max_count": 10 }
3. merge template: { "max_count": 5 } → result = { "max_count": 5 }

✅ Final result: max_count = 5 (from template)
```

### Example 2: Template with null keeps preset value

```json
// Config levels:
user_config:  { "max_count": 999 }
preset:       { "max_count": 10 }
template:     { "max_count": null }

// Merging:
1. base = { "max_count": 999 }
2. merge preset: { "max_count": 10 } → result = { "max_count": 10 }
3. merge template: { "max_count": null } → SKIP → result = { "max_count": 10 }

✅ Final result: max_count = 10 (from preset, template null is ignored)
```

### Example 3: All nulls fall back to user_config

```json
// Config levels:
user_config:  { "max_count": 999 }
preset:       { "max_count": null }
template:     { "max_count": null }

// Merging:
1. base = { "max_count": 999 }
2. merge preset: { "max_count": null } → SKIP → result = { "max_count": 999 }
3. merge template: { "max_count": null } → SKIP → result = { "max_count": 999 }

✅ Final result: max_count = 999 (from user_config default)
```

### Example 4: Key not specified = same as null

```json
// Config levels:
user_config:  { "max_count": 999 }
preset:       { "topics_display": {} }  // no max_count key
template:     { "topics_display": {} }  // no max_count key

// Merging:
1. base = { "max_count": 999 }
2. merge preset: {} → no max_count key → result = { "max_count": 999 }
3. merge template: {} → no max_count key → result = { "max_count": 999 }

✅ Final result: max_count = 999 (from user_config)
```

## Use Cases for `null`

### ✅ When to use `null`:

1. **"Use preset/user_config default"**
   ```json
   {
     "template": {
       "topics_display": {
         "max_count": null  // use preset or user_config value
       }
     }
   }
   ```

2. **"Don't override this specific field"**
   ```json
   {
     "template": {
       "topics_display": {
         "format": "numbered_list",  // override
         "max_count": null,           // don't override
         "prefix": "Topics:"          // override
       }
     }
   }
   ```

3. **"Platform-specific: one overrides, another uses default"**
   ```json
   {
     "youtube": {
       "topics_display": {
         "max_count": 10  // override for YouTube
       }
     },
     "vk": {
       "topics_display": {
         "max_count": null  // use preset/user_config for VK
       }
     }
   }
   ```

### ❌ When NOT to use `null`:

1. **To explicitly clear a value** - use empty string `""` or `0` instead
2. **To disable a feature** - use `enabled: false` or specific flag

## Comparison: Not Specified vs `null` vs `0`

| Notation | Meaning | Result (if base=999) |
|----------|---------|----------------------|
| Key not specified | Use base value | 999 |
| `"max_count": null` | Use base value | 999 |
| `"max_count": 0` | Explicit value: 0 | 0 (no limit applied) |
| `"max_count": 999` | Explicit value: 999 | 999 |
| `"max_count": 10` | Explicit value: 10 | 10 |

## Real-World Example: Your Case

**Your database config:**

```json
// VK Preset (id=3):
{
  "topics_display": {
    "max_count": null  // ← explicitly set to null
  }
}

// YouTube Preset (id=2):
{
  "topics_display": {
    // max_count not specified at all
  }
}

// User Config (id=2):
{
  "topics_display": {
    "max_count": 10  // old default (before update to 999)
  }
}
```

**What happened:**

1. **VK:**
   - User config: `max_count = 10`
   - Preset merge: `max_count = null` → **SKIPPED**
   - Template merge: `max_count = null` → **SKIPPED**
   - **Final: 10** (from user config)
   
   **But wait!** Your VK showed **50 topics**, not 10. This means either:
   - Your user config had `max_count = 50` or higher
   - Or there was a bug in the old code

2. **YouTube:**
   - User config: `max_count = 10`
   - Preset merge: key not specified → no change
   - Template merge: key not specified → no change
   - **Final: 10** (from user config) ✅ Matches your output!

## Summary: Is `null` Needed?

**YES, `null` is useful and necessary:**

1. ✅ **Semantic clarity:** Explicitly saying "use default" vs accidentally omitting
2. ✅ **Flexibility:** Can override some fields while keeping others as-is
3. ✅ **Platform-specific configs:** Override for one platform, use default for another
4. ✅ **Template reusability:** One template can work with different presets

**Current behavior is correct and well-designed!** 🎯
