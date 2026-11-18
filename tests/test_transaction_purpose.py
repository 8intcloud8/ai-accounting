import sqlite3
from test_supplier_links import SupplierLinkTests
from accounting_store import connect
from product_store import audit, status_report
import transaction_purpose
import proposal_store
import bas_dashboard

class TransactionPurposeTests(SupplierLinkTests):
    def purpose(self,**changes):
        req={'business_id':'example','account_id':'personal-9206','source_nickname':'Personal','start':'2026-07-01','end':'2026-09-30','confirmed_by':'user','records':[{'transaction_id':2,'purpose':'Shared','category':'Electricity','outside_bas':True,'reason':'User confirmed shared electricity, retain outside BAS'}]}
        req.update(changes)
        return transaction_purpose.record(self.path,req,connect,audit)
    def test_shared_is_audited_classified_without_money_changes(self):
        with connect(self.path) as c:before=[c.execute('select * from '+t).fetchall() for t in ('journals','journal_lines','gst_items')]
        self.assertEqual(self.purpose()['saved_purposes'],1);self.assertEqual(self.purpose()['saved_purposes'],0)
        with connect(self.path) as c:
            self.assertEqual(before,[c.execute('select * from '+t).fetchall() for t in ('journals','journal_lines','gst_items')])
            rows=proposal_store.transaction_rows(c,'2026-07-01','2026-09-30')
            self.assertEqual(rows[1][6],'Classified');self.assertEqual(rows[1][-1],'Shared');self.assertEqual(rows[1][7],'Electricity');self.assertEqual(rows[1][9],0)
            c.row_factory=sqlite3.Row
            self.assertEqual(status_report(c,'2026-07-01','2026-09-30')['unclassified_transactions'],1)
        self.assertEqual(bas_dashboard.purpose_counts(self.path,'2026-07-01','2026-09-30')['Shared'],1)
    def test_purpose_alone_does_not_close_unposted_business_gst(self):
        self.purpose(records=[{'transaction_id':2,'purpose':'Shared','category':'Electricity','outside_bas':False,'reason':'Allocation not determined'}])
        with connect(self.path) as c:self.assertEqual(transaction_purpose.outside_ids(c),set())
    def test_source_change_reopens_review(self):
        self.purpose()
        with connect(self.path) as c:c.execute('update transactions set debit_cents=999 where id=2')
        with connect(self.path) as c:self.assertEqual(transaction_purpose.reviewed(c),{})
    def test_rejects_wrong_account_unconfirmed_and_invalid_purpose(self):
        for change in ({'account_id':'company'},{'confirmed_by':'assistant'},{'records':[{'transaction_id':2,'purpose':'Other','category':'Electricity','outside_bas':True,'reason':'x'}]}):
            with self.assertRaises(ValueError):self.purpose(**change)

    def test_outside_review_and_supplier_link_are_mutually_exclusive(self):
        self.purpose()
        with self.assertRaises(ValueError):
            self.record(dict(self.req,links=[{'transaction_id':2,'journal_id':1,'amount_cents':1100}]))
        self.purpose(records=[{'transaction_id':2,'purpose':'Shared','category':'Electricity','outside_bas':False,'reason':'Reopen for supported allocation'}])
        self.record(dict(self.req,links=[{'transaction_id':2,'journal_id':1,'amount_cents':1100}]))
        with self.assertRaises(ValueError):self.purpose()

    def test_changed_purpose_invalidates_review_digests(self):
        from product_store import state_digest
        from bas_applicability import ledger_digest
        with connect(self.path) as c:before=(state_digest(c),ledger_digest(c))
        self.purpose()
        with connect(self.path) as c:after=(state_digest(c),ledger_digest(c))
        self.assertNotEqual(before[0],after[0]);self.assertNotEqual(before[1],after[1])
