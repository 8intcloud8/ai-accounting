"""Email invoice checklist: safe rendering, right mailbox link, save request carries message ids."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/search-email-invoices/skills/search-email-invoices/scripts"))
from render_checklist import render  # noqa: E402

BILL = {"threadId": "t1", "messageId": "m9", "date": "2026-07-09", "vendor": "<b>Evil</b>",
        "sender": {"email": "billing@example.com"}, "subject": "Invoice", "attachments": ["inv.pdf"],
        "gmailLink": "https://mail.google.com/mail/u/0/#all/t1"}
RESULT = {"category": "business", "dateFrom": "2026-07-01", "dateTo": "2026-09-30", "bills": [BILL]}


class RenderTest(unittest.TestCase):
    def test_single_account_link_opens_that_mailbox(self):
        page = render(RESULT, ["me@example.com"])
        self.assertIn('href="https://mail.google.com/mail/?authuser=me%40example.com#all/t1"', page)

    def test_several_accounts_keep_the_plain_link(self):
        self.assertIn("mail/u/0/#all/t1", render(RESULT, ["a@example.com", "b@example.com"]))

    def test_row_carries_message_to_save_and_escapes_email_text(self):
        page = render(RESULT, ["me@example.com"])
        self.assertIn('data-message="m9"', page)
        self.assertIn("message ids: ", page)
        self.assertNotIn("<b>Evil</b>", page)

    def test_non_gmail_link_is_dropped(self):
        page = render(dict(RESULT, bills=[dict(BILL, gmailLink="https://evil.example/#all/t1")]), ["x@example.com"])
        self.assertNotIn("evil.example", page)

    def test_file_page_hides_folder_picker_and_keeps_workspace_folder(self):
        page = render(RESULT, ["me@example.com"], "/ws/invoices")
        self.assertIn('value="/ws/invoices"', page)
        self.assertIn("hidePicker()", page)
