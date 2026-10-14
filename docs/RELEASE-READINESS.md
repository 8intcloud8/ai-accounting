# Release readiness

## Implemented in 0.2.0-beta

Separate plugins distributed as a suite; canonical runtime and generated copies; workspace/profile setup; managed document copies; audited corrections/reversals; balanced journals; GST control checks; statement reconciliation; persistent workflow review checkpoints; draft BAS and tax workpapers; consistent backup/new-folder restore; automated regression and package checks.

## Public release gates

- Run the installer in a fresh Codex profile with host plugin discovery. Config-file registration alone does not establish runtime discovery in every host version.
- Verify local-file flow and Gmail search/save in that profile; Gmail requires user connection.
- Package or resolve host runtimes without requiring ordinary users to manage Python/Node. The beta installer uses existing runtimes and installs project dependencies; it does not ship operating-system runtimes.
- Extend special GST cases and period finalisation/amendment rules before claiming complete BAS functionality.
- Extend annual tax schedules, opening balance workflows and accountant-reviewed calculation fixtures before claiming tax-return generation.
- Test restore from an exported workspace and schema upgrades from each supported release.
- Have representative anonymised Australian accounting cases independently reviewed. Code tests do not certify tax treatment.

The installer and reporting commands must report limitations explicitly. No automated lodgement is implemented.
