# Release readiness

## Implemented in 0.2.0-beta

Separate plugins distributed as a suite; canonical runtime and generated copies; workspace/profile setup; managed document copies; audited corrections/reversals; balanced journals; GST control checks; statement reconciliation; persistent workflow review checkpoints; draft BAS and tax workpapers; consistent backup/new-folder restore; automated regression and package checks.

## Public release gates

- Run the installer in a fresh Codex profile with host plugin discovery. Config-file registration alone does not establish runtime discovery in every host version. The marketplace manifest and all 12 plugin manifests declare `interface`/`category`/`policy` metadata verified against the real Codex marketplace parser (`openai/codex` `core-plugins/src/marketplace.rs`: `installation` ∈ {AVAILABLE, INSTALLED_BY_DEFAULT, NOT_AVAILABLE}, `authentication` ∈ {ON_INSTALL, ON_USE}); a marketplace-sourced install self-builds the two Gmail MCP servers on first launch since `dist/` is gitignored. None of this has been click-tested against the live Desktop Plugins Directory yet.
- Replace the `network_access` config prerequisite with a zero-config delivery path before general release. Codex's default sandbox denies shell commands all network access including `127.0.0.1` (verified in `openai/codex` `codex-rs/sandboxing/src/seatbelt.rs`: with network disabled and no proxy/unix-socket config the emitted policy is empty, so seatbelt default-denies the loopback bind; reproduced as `PermissionError` EPERM under `sandbox-exec -f '(deny network*)'`). `review-invoices` therefore cannot quarantine or restore at all for a default install, and `search-email-invoices` loses its folder picker. No plugin manifest can request this: every `RequirementSource` in `codex-rs/config/src/config_requirements.rs` is MDM/enterprise/system-managed. Both scripts now fail with the exact remedy instead of degrading silently, and README documents it as an install step — but requiring a hand-edited config file is not acceptable for general availability. MCP server processes are **not** sandboxed (`codex-rs/codex-mcp/src/sandbox_metadata.rs` forwards the policy for *voluntary* self-sandboxing), so serving these checklists from an MCP server — or from a child process it spawns — is the identified fix.
- Verify local-file flow and Gmail search/save in that profile; Gmail requires user connection.
- Package or resolve host runtimes without requiring ordinary users to manage Python/Node. The beta installer uses existing runtimes and installs project dependencies; it does not ship operating-system runtimes.
- Extend special GST cases and period finalisation/amendment rules before claiming complete BAS functionality.
- Extend annual tax schedules, opening balance workflows and accountant-reviewed calculation fixtures before claiming tax-return generation.
- Test restore from an exported workspace and schema upgrades from each supported release.
- Have representative anonymised Australian accounting cases independently reviewed. Code tests do not certify tax treatment.

The installer and reporting commands must report limitations explicitly. No automated lodgement is implemented.
