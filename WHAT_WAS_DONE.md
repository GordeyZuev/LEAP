# Change Log

## 2026-01-23: Added Credential Validation for Presets and Sources

### Changes
- Added validation for `credential_id` when creating output presets and input sources
- Prevents foreign key constraint violations by validating credentials at application layer
- Returns HTTP 404 with clear error message instead of HTTP 500 database error

### Files Modified
- `api/routers/output_presets.py`: Added credential validation in `create_preset()` endpoint
- `api/routers/input_sources.py`: Replaced manual validation with `ResourceAccessValidator` in `create_source()` endpoint

### Example Error
- Invalid credential: `credential_id=4` → HTTP 404: "Cannot create preset: credential 4 not found or access denied"

## 2026-01-23: Added Date and Period Validation

### Changes
- Added input validation for date parameters and period format (YYYYMM)
- Prevents 500 errors from invalid user input, returns HTTP 400 with clear error messages

### Files Modified
- `utils/date_utils.py`: Added `InvalidDateFormatError`, `InvalidPeriodError`, `validate_period()` function
- `api/routers/recordings.py`: Added error handling for `from_date` and `to_date` parameters (2 locations)
- `api/routers/admin.py`: Added validation for `period` parameter in `/stats/quotas`
- `api/routers/users.py`: Added validation for `period` parameter in `/me/quota/history`

### Example Errors
- Invalid date: `2026-20-01` → HTTP 400: "Invalid date format: '2026-20-01'. Supported formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD-MM-YY, DD/MM/YY"
- Invalid period: `202613` → HTTP 400: "Invalid month: 13 in period 202613. Month must be 01-12"
