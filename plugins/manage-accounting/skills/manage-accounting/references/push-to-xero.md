# Push the books into the user's Xero

Use when the user asks to move, send, sync or push their books to Xero. Nothing goes to
Xero without the user's OK for the batch, because it is their live ledger.

1. Xero tools: the Xero MCP tools (`list-accounts`, `list-contacts`, `create-contact`,
   `create-bank-transaction`) must be available. If not, use the `setup-xero-mcp` skill
   first. Confirm the Xero organisation name with `list-organisation-details`.
2. Plan: `scripts/accounting_store.py --db <db> xero-push-plan --start <start> --end <end>`.
   - `unlinked_bank_accounts`: for each, call `list-accounts`, show the user the Xero bank
     accounts (type BANK) and ask which one it is, or whether it stays out (a personal card
     usually stays out). Link with `xero-link-bank --request '{"account": "<ours>",
     "xero_account_id": "<AccountID>", "xero_name": "<name>"}'`, then plan again.
   - `accounts_used`: every code must exist in Xero (`list-accounts`). The chart here
     follows Xero's Australian default, so most do. List any missing ones and ask the user
     to add them in Xero (Accounting > Chart of accounts) or to recode here first.
   - `held`: say why each is held (GST not decided, or GST Xero would calculate
     differently). They are not sent.
3. Ask once: "Send N transactions (total $X out, $Y in) to <organisation>?" Mention that if the
   Xero bank account has a bank feed, the user should reconcile them in Xero with the
   **Match** tab, never **Create**, or they would be counted twice.
4. Send: for each `ready` item, find the contact by payee (`list-contacts` with
   `searchTerm`; create it with `create-contact` when none matches), then call
   `create-bank-transaction` with `type`, `bankAccountId`, `contactId`, `date`, `reference`
   and `lineItems` exactly as planned (amounts exclude GST; Xero adds it from `taxType`).
5. Record after every few successes: `xero-mark-pushed --request '{"pushed":
   [{"journal_id": <id>, "xero_id": "<BankTransactionID>"}]}'`. A repeat plan then skips
   them. Stop on the first error, record what succeeded, and report the error plainly.
6. Report: how many were sent, the Xero links the tool returned, and what was held.
