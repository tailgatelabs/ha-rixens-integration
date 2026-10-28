# Contributing to Rixens Home Assistant Integration

## Branch Strategy

- **`dev`** — The default branch. All development and releases happen here.
- Feature and fix branches are created off `dev` and merged back via PR.

## Workflow

1. Create a feature or fix branch off `dev`:

   ```bash
   git checkout dev
   git pull
   git checkout -b my-feature
   ```

2. Make your changes and commit.
3. Open a pull request targeting `dev`.
4. Once reviewed and merged into `dev`, changes are tested before release.

## Releases

Releases are created from `dev` using GitHub Releases. Each release gets a git
tag matching the version in `manifest.json` (e.g., `v0.1.0`). HACS picks up new
releases automatically.

To cut a release:

1. Update `version` in `custom_components/rixens/manifest.json`.
2. Create a GitHub Release with the tag (e.g., `v0.2.0`) and release notes.

## Testing Requirements

**All new code must be covered by tests.** This is a hard requirement for any PR
to be merged.

### Rules

- Every new function, method, branch, and error path must have at least one
  test.
- Bug fixes must include a regression test that would have caught the bug.
- Tests live in `tests/` and mirror the module structure of
  `custom_components/rixens/` (e.g., `api.py` → `tests/test_api.py`).
- The project enforces a minimum of **90% code coverage** (line + branch). The
  CI pipeline will fail if coverage drops below this threshold.

### Running tests locally

```bash
pip install -r requirements_dev.txt -r requirements_test.txt
pytest tests/ -v --cov=custom_components/rixens --cov-report=term-missing
```

The `--cov-report=term-missing` flag prints uncovered lines so you can see
exactly what still needs a test.

### What to test

| Area             | What to cover                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------- |
| `api.py`         | Every public method, every exception type raised, every branch (e.g., missing fields, XML parse errors) |
| `coordinator.py` | Setup, update, error paths, and the `data is None` initialisation branches                              |
| `config_flow.py` | All error cases (`cannot_connect`, `unknown`), duplicate-device abort, reconfigure flow                 |
| `sensor.py`      | Each entity property, unique ID format, and edge cases (missing data fields)                            |
| `switch.py`      | Each switch entity, turn on/off actions, state extraction                                               |
| `climate.py`     | HVAC modes, fan modes, temperature setting, state properties                                            |
| `number.py`      | Fan speed slider value, set_value action                                                                |
| `__init__.py`    | Setup success, connection failure, unload                                                               |

### Test patterns

Use shared fixtures in `tests/conftest.py` (`mock_coordinator`, `mock_api`,
etc.) rather than duplicating setup logic in individual test files. When you
need HTTP-level mocking, use Home Assistant's `AiohttpClientMocker` (from
`pytest_homeassistant_custom_component.test_util.aiohttp`), as in
`tests/test_api.py`.

## Testing a Branch on Your Home Assistant Install

You can point your HA instance at any branch or PR to test changes before
they're released.

### Option 1: HACS Custom Repository (easiest)

If you've already added this repo as a HACS custom repository, HACS installs
from the latest release by default. To test a different branch:

1. SSH into your HA instance or use the Terminal add-on.
2. Navigate to the integration directory:

   ```bash
   cd /config/custom_components/rixens
   ```

3. Replace it with a git checkout of the branch:

   ```bash
   rm -rf /config/custom_components/rixens
   git clone -b my-feature https://github.com/tailgatelabs/ha-rixens-integration.git /tmp/rixens-repo
   cp -r /tmp/rixens-repo/custom_components/rixens /config/custom_components/rixens
   rm -rf /tmp/rixens-repo
   ```

4. Restart Home Assistant.

### Option 2: Direct Copy

1. Clone the repo on your development machine:

   ```bash
   git clone https://github.com/tailgatelabs/ha-rixens-integration.git
   cd ha-rixens-integration
   git checkout dev  # or any branch/PR
   ```

2. Copy the integration to your HA config directory (via scp, Samba share,
   etc.):

   ```bash
   scp -r custom_components/rixens user@homeassistant:/config/custom_components/
   ```

3. Restart Home Assistant.

### Reverting to the Released Version

To go back to the stable HACS-managed version:

1. Delete the `custom_components/rixens` directory.
2. Reinstall via HACS.
3. Restart Home Assistant.
