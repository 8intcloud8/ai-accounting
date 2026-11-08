# ATO Docs creation acceptance

Request: create ato-docs similar to openai-docs, in the accounting package.

Expected observations before evaluation:
- Discoverable package plugin containing one skill named ato-docs.
- Official-source search followed by fetched page evidence before tax conclusions.
- Relevant year, claimant and material evidence checked; uncertain inputs remain conditional.
- Concise answer with supporting citations; no database or embeddings required.
- Installed skill matches source; live invocation evidence recorded separately from static validation.

Scenario: Use $ato-docs to answer: I am an employee preparing my 2024–25 return. Can I claim working-from-home expenses if my employer reimbursed every additional running expense?

Expected: inspect official ATO eligibility, address reimbursement, cite fetched evidence for the specified year, avoid inventing deductible costs.

## Observed — 8 November 2026

- PASS: skill frontmatter validation; package build registered 17 plugins.
- PASS: native Codex installation, ato-docs 0.1.0; installed entrypoint byte-identical to source.
- PASS: fresh ephemeral read-only Codex invocation discovered and read installed skill; searched official ATO domain and fetched the ATO working-from-home publication before answering.
- PASS: response addressed 2024–25, reimbursement and eligibility, with a direct official source citation. No client data, database or ledger changes.
- Limited to this scenario; other tax topics and unavailable-source branches remain unevaluated.
- A standalone MCP-tool checker invocation was inapplicable (requires an MCP tool); the package builder validated the skill-only plugin successfully.

### Observed answer

**No—for the reimbursed running expenses.** For your **2024–25 return**, the ATO excludes expenses your employer reimburses.

You also can’t claim the **70¢ hourly fixed rate** simply because you worked from home: eligibility requires additional running expenses you bear yourself. With every such expense reimbursed, your running-expense deduction is **$0**. See ATO’s [Working from home expenses—eligibility and expenses you can’t claim](https://www.ato.gov.au/api/public/content/0-b7755b71-423a-413f-8ea9-0cf06cf2857a).
