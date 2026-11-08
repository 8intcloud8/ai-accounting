---
name: setup-accounting
description: Configure the local accounting workspace and business profile once, then show next steps.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/agent-harness.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Set up Accounting



Ask for the accounting folder, legal business name, entity type and stable business ID. Reuse known details. Ask whether GST registered and cash/accrual basis; unknown stays null/unknown. One business per workspace. Support AUD initially.

Create the workspace at the user's chosen folder with `db/`, `documents/`, `output/YYYY-MM-DD/reports/`, and `backups/`. Use `scripts/accounting_store.py --db <folder>/db/accounting.db setup-accounting --request <profile.json>`; paths are relative to this skill. Profile example:
```json
{"business_id":"example-business","legal_name":"Example Business","entity_type":"sole_trader","gst_registered":null,"gst_basis":"unknown"}
```
Never assign a guessed GST basis. Existing populated workspaces must retain their existing business ID. A second business needs another workspace. Set `AI_ACCOUNTING_DB` to the selected workspace for every subsequent command, or use the installed workspace selector. Show the folder and next input needed; users do not administer SQLite.

For first-time package installation, use the suite's `scripts/install.py` with the selected workspace and profile. It can build dependencies in an isolated environment with `--dependencies`; `--local-only` skips email plugins. Use a Python 3.11+ runtime available from the host. Explain a missing runtime/build prerequisite precisely. Never claim installation until command succeeds and plugin paths resolve.

If GST settings were initially unknown, use `update-profile --request <JSON>` with gst_registered, gst_basis and a reason. Existing reviewed GST entries must be reversed/reviewed before changing tax settings.

## Confirm reporting scope

Run `configure-reporting --request <JSON>` after verifying the BAS reporting method and all relevant bank/card account names. Example: `{"method":"simpler","expected_accounts":["CBA business","Credit card"],"evidence":"User confirmed reporting method and full account inventory"}`. Supported methods are simpler/full/instalments/unknown; only confirmed simpler can pass this version's BAS scope gate. Do not invent eligibility from GST registration. Missing expected account-period evidence blocks readiness. The package reports G1 GST-inclusive; communicate that convention. PAYG and other labels remain separate checks.

## Identify the BAS work required

Reuse saved period applicability. Route missing or stale applicability facts to `grill-me-tax`; it owns the period interview and persistence. Validate its saved results before reporting readiness; do not repeat the interview here.
