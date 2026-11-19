# AI Accounting

Do your bookkeeping and BAS by chatting with Codex. Give it your bank statements and invoices. It sorts them, works out the GST and prepares your BAS.

- Your files stay on your computer.
- It never lodges anything. You or your accountant check it and lodge.

**You need:** a Mac, the internet, and about 5 minutes.

## Install

### 1. Get Codex

Download the Codex app from [openai.com/codex](https://openai.com/codex/) (or use the ChatGPT desktop app with Codex). Open it and sign in.

### 2. Add AI Accounting

1. In Codex, open **Plugins**.
2. Click **Add marketplace**.
3. Paste this and save:

   ```
   https://github.com/8intcloud8/ai-accounting.git
   ```

4. Choose **AI Accounting** in the plugin list. If its plugins are not installed already, click **Install** on each one.

### 3. Start

1. Quit Codex completely: press `⌘ Command` + `Q`.
2. Open Codex again and start a new chat.
3. Type: **Set up my accounting**

Codex asks a few questions about your business, then guides you. If it needs anything else on your Mac, it asks you first and installs it.

<details>
<summary>Can't find Plugins? Install with Terminal instead</summary>

1. Press `⌘ Command` + `Space`, type **Terminal**, press `Return`.
2. Paste this line and press `Return`:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/8intcloud8/ai-accounting/main/scripts/install.sh | sh
   ```

3. Wait for **Done**. If a window asks to install **developer tools**, click **Install**, then paste the line again. If it says **Install Python**, get it from [python.org/downloads](https://www.python.org/downloads/).
4. Go to step 3 above.

</details>

## Using it

Type what you want in the chat, in your own words:

- "Here are my bank statements" (then drag the files into the chat)
- "Do my BAS for July to September"
- "Show my BAS"

Codex keeps working by itself and only stops when it needs you.

## Update

In **Plugins**, update the AI Accounting marketplace, then quit and reopen Codex.

## Help

- **Codex doesn't know about accounting:** quit Codex with `⌘ Command` + `Q`, open it again, start a new chat.
- **Something else:** tell Codex in the chat, or [open an issue](https://github.com/8intcloud8/ai-accounting/issues). Never post your bank statements, invoices or tax details there.

Treat the BAS as a draft for you or your accountant to check. Mac only for now.

Developers: see [DEVELOPERS.md](DEVELOPERS.md).
