# AI Accounting

Do your bookkeeping and BAS by chatting with Codex. Give it your bank statements and invoices. It sorts them, works out the GST and prepares your BAS.

- Your files stay on your computer.
- It never lodges anything. You or your accountant check it and lodge.

**You need:** a Mac, the internet, and about 10 minutes.

## Install

### 1. Get Codex

Download the Codex app from [openai.com/codex](https://openai.com/codex/). Open it and sign in.

### 2. Open Terminal

Press `⌘ Command` + `Space`, type **Terminal**, press `Return`. A window with text opens. That's normal.

### 3. Paste this line and press `Return`

```sh
curl -fsSL https://raw.githubusercontent.com/8intcloud8/ai-accounting/main/scripts/install.sh | sh
```

To copy it, click the copy button on the box above, or select the line and press `⌘ Command` + `C`. Paste it with `⌘ Command` + `V`.

Wait until you see **Done**.

**If you see one of these messages instead:**

| Message | What to do |
|---|---|
| A window asks to install **developer tools** | Click **Install**, wait for it to finish, then do step 3 again. |
| **Install Python** | Go to [python.org/downloads](https://www.python.org/downloads/), click the yellow Download button, open the file and click **Continue** until it finishes. |
| **Codex was not found** | Do step 1, then step 3 again. |

### 4. Start

1. Quit Codex completely: click on Codex, then press `⌘ Command` + `Q`.
2. Open Codex again and start a new chat.
3. Type: **Set up my accounting**

Codex asks a few questions about your business, then guides you.

## Using it

Type what you want in the chat, in your own words:

- "Here are my bank statements" (then drag the files into the chat)
- "Do my BAS for July to September"
- "Show my BAS"

Codex keeps working by itself and only stops when it needs you.

## Update

Do step 3 again, then quit and reopen Codex.

## Help

- **Codex doesn't know about accounting:** quit Codex with `⌘ Command` + `Q`, open it again, start a new chat.
- **Something else:** tell Codex in the chat, or [open an issue](https://github.com/8intcloud8/ai-accounting/issues). Never post your bank statements, invoices or tax details there.

Treat the BAS as a draft for you or your accountant to check. Mac only for now.

Developers: see [DEVELOPERS.md](DEVELOPERS.md).
