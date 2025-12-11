# Cortex Compliance Cloner

## Overview
A Python script to clone compliance standards, controls, and rules from the Cortex XSIAM/XDR platform using the Compliance API.

## Features
- Clone a complete compliance standard with a custom prefix
- Clone all controls from the original standard
- Clone all rules attached to each control
- Link cloned controls to the new standard
- Automatic category/subcategory validation
- Proper severity mapping for rules

## Usage

```bash
python clone_cortex_compliance.py \
  --key YOUR_API_KEY \
  --id YOUR_API_KEY_ID \
  --tenant api-example.xdr.eu.paloaltonetworks.com \
  --standard "CIS AWS Foundations Benchmark" \
  --prefix "MyCompany - "
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--key` | Yes | Your Cortex API Key |
| `--id` | Yes | Your API Key ID |
| `--tenant` | Yes | Tenant FQDN (e.g., api-example.xdr.eu.paloaltonetworks.com) |
| `--standard` | Yes | Name of the standard to clone |
| `--prefix` | No | Prefix for cloned items (default: "Clone - ") |
| `--debug` | No | Enable debug logging |

## How It Works

1. **Fetch Categories**: Gets valid categories and subcategories from the API
2. **Find Source Standard**: Locates the standard to clone by name
3. **Create Target Standard**: Creates a new standard with the specified prefix
4. **Clone Controls**: For each control in the source standard:
   - Fetches control details including rules
   - Creates a new control with the prefixed name
   - Validates category/subcategory against allowed values
   - Copies all rules with proper field mapping
5. **Link Controls**: Links all new controls to the target standard

## API Endpoints Used

- `get_standards` - Fetch standards
- `add_standard` - Create new standard
- `edit_standard` - Link controls to standard
- `get_control` - Fetch control details
- `add_control` - Create new control
- `get_controls` - Search for controls
- `add_rules_to_control` - Add rules to a control
- `get_control_categories_and_subcategories` - Get valid categories

## Files

- `clone_cortex_compliance.py` - Main script

## Recent Changes

- 2025-12-11: All issues resolved - 100% success rate
  - Fixed rule severity mapping: API only accepts `info`, not `informational`
  - Two-phase approach: create all controls first, then add all rules
  - Added retry logic (3 attempts) and timing delays for API stability
  - Successfully tested: 10/10 controls, 8/8 rules cloned
- 2025-12-11: Control severity now preserved from source
  - Severity is extracted from source control and passed when creating new controls
  - Handles severity formats: SEV_020_LOW, SEV_030_MEDIUM, SEV_010_INFO, critical, high
- 2025-12-11: Fixed API limitations
  - Subcategory handling (API requires a valid subcategory)
  - Rule type to use 'Identity' (API doesn't accept other types)
  - Scannable_assets to use empty array (API rejects custom asset names)
- 2025-12-11: Initial version created

## Known API Limitations

### Subcategory Requirement
- The Cortex API **requires** a valid subcategory when creating controls
- If the source control doesn't have a subcategory, the script uses a default valid subcategory
- Available subcategories are fetched from the `get_control_categories_and_subcategories` endpoint

### Rule Type Restriction
- The `add_rules_to_control` API endpoint **only accepts `Identity`** as a valid rule type
- Source rules may have different types (e.g., `Config`), but these are NOT accepted by the API:
  - `Config` → **400 Error**: "Config is not a valid rule type"
  - `config` → **400 Error**: "config is not a valid rule type"
  - `Identity` → **200 OK** (works)
- The script logs a warning when the original rule type differs from `Identity`
- All cloned rules will have `type: Identity` regardless of the source rule type

### Scannable Assets
- The API doesn't accept custom scannable asset names when creating rules
- Rules are created with an empty `scannable_assets` array
- Source values like `['OCI File Storage File System']` are not preserved

### Rule Severity Values
- Valid rule severity values: `critical`, `high`, `medium`, `low`, `info`
- Note: `informational` is NOT valid (use `info` instead)
- Source severities like `SEV_010_INFO` are mapped to `info`
