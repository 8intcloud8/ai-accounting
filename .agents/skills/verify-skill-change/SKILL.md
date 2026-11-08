---
name: verify-skill-change
description: Verify a changed or reinstalled accounting skill against the current ticket using its installed entry point and observable results.
---

1. Take the user's change request as the ticket. Before editing, turn each requirement into a concrete observation that would distinguish success from failure. For a reinstall, reuse the most recent applicable ticket. Record expected behaviour before running the scenario.
2. Implement the change, run relevant existing regression checks, reinstall the affected plugins through Codex and verify the installed files match the build. Record the installed version.
3. Exercise the installed skill with an ordinary user prompt that triggers the changed behaviour. Keep the expected answer out of the prompt. Use a fresh invocation where available. For Gmail requirements use the connected Gmail accounts and real searches. Derive expected counts from accounts successfully searched in that run. Use an isolated folder for downloads and an isolated workspace for ledger writes. Respect actual approval prompts.
4. Observe what the user would see. Check the conversation for unwanted prompts, inspect the rendered browser for UI criteria, and verify actual file paths and contents for save criteria. Choose checks from this ticket. Installation, source inspection and the skill's own claims cannot establish behavioural success.
5. Record each requirement, expected and observed behaviour, and pass, fail or blocked with concise evidence. Keep private email details out of the ticket. Fix failures, reinstall, then repeat affected scenarios. If a required branch never occurred or a needed connection was unavailable, mark it unverified and explain why. Claim completion only when all criteria pass.
