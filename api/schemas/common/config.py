"""Base Pydantic model configurations"""

from pydantic import ConfigDict

# Base configuration for all schemas
# Keep order of fields as in class definition (not sorted alphabetically)
BASE_MODEL_CONFIG = ConfigDict(
    # Keep order of fields in JSON Schema
    json_schema_serialization_defaults_required=True,
    # Allow populate_by_name for ORM compatibility
    populate_by_name=True,
    # Strict validation of types
    strict=False,
    # Use enum values instead of names
    use_enum_values=False,
)

# Configuration for ORM models (response schemas)
ORM_MODEL_CONFIG = ConfigDict(
    from_attributes=True,
    json_schema_serialization_defaults_required=True,
    populate_by_name=True,
)
