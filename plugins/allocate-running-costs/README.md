# Allocate Running Costs

Calculate business and personal shares of utility and running costs with evidence and GST status.

This independently installable plugin contains one skill: `allocate-running-costs`. Register this folder with your assistant host. Python 3.10+ is required.

The bundled SQLite helper uses the same `~/.ai-accounting/accounting.db` as the other accounting plugins and honours `AI_ACCOUNTING_DB`. It requires no database server. Existing records are reused; do not create a separate database per plugin.

Resolve `scripts/accounting_store.py` relative to `skills/allocate-running-costs/`. The bundled storage modules use only the Python standard library.

See the skill for source-evidence, review and confirmation requirements. Installing this plugin does not install the other accounting skills.
