---
name: setup-accounting
description: Configure the local accounting workspace and business profile once, then show next steps.
---

# Set up Accounting

Ask for the accounting folder, legal business name, entity type and stable business ID. Reuse known details. Ask whether GST registered and cash/accrual basis; unknown stays null/unknown. One business per workspace. Support AUD initially.

Create the workspace at the user's chosen folder with `db/`, `documents/`, `output/YYYY-MM-DD/`, and `backups/`. Use `scripts/accounting_store.py --db <folder>/db/accounting.db setup-accounting --request <profile.json>`; paths are relative to this skill. Profile example:
```json
{"business_id":"example-business","legal_name":"Example Business","entity_type":"sole_trader","gst_registered":null,"gst_basis":"unknown"}
```
Never assign a guessed GST basis. Existing populated workspaces must retain their existing business ID. A second business needs another workspace. Set `AI_ACCOUNTING_DB` to the selected workspace for every subsequent command, or use the installed workspace selector. Show the folder and next input needed; users do not administer SQLite.

For first-time package installation, use the suite's `scripts/install.py` with the selected workspace and profile. It can build dependencies in an isolated environment with `--dependencies`; `--local-only` skips email plugins. Use a Python 3.11+ runtime available from the host. Explain a missing runtime/build prerequisite precisely. Never claim installation until command succeeds and plugin paths resolve.

If GST settings were initially unknown, use `update-profile --request <JSON>` with gst_registered, gst_basis and a reason. Existing reviewed GST entries must be reversed/reviewed before changing tax settings.

## Confirm reporting scope

Run `configure-reporting --request <JSON>` after verifying the BAS reporting method and all relevant bank/card account names. Example: `{"method":"simpler","expected_accounts":["CBA business","Credit card"],"evidence":"User confirmed reporting method and full account inventory"}`. Supported methods are simpler/full/instalments/unknown; only confirmed simpler can pass this version's BAS scope gate. Do not invent eligibility from GST registration. Missing expected account-period evidence blocks readiness. The package reports G1 GST-inclusive; communicate that convention. PAYG and other labels remain separate checks.
