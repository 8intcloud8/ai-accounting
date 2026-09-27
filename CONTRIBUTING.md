# Contributing

Place new plugins under `plugins/`, with their skills, documentation, and dependencies inside that folder. Avoid dependencies on sibling plugins' internal files. Document optional integrations explicitly.

Run each affected plugin's typecheck, tests where available, and build. Extend the root CI matrix for new Node plugins; add separate jobs for other runtimes. Use synthetic financial data in tests. Never commit personal documents, settings, credentials, or signed URLs.

Contributions are under the MIT License.
