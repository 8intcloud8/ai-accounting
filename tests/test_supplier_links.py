import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'accounting_core'))
from accounting_store import connect, import_approved
from product_store import setup, audit, status_report
import supplier_links
import proposal_store
import bas_dashboard

class SupplierLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.path=self.root/'db/accounting.db'
        setup(self.path,{'business_id':'example','legal_name':'Example','entity_type':'company','gst_registered':True,'gst_basis':'accrual'},connect)
        src=self.root/'bank.csv';src.write_text('fixture')
        import_approved(self.path,src,'personal-9206',{'decision':'approved','rows':[{'date':'01/07/2026','description':'Supplier','debit':'11.00'},{'date':'02/07/2026','description':'Supplier','debit':'11.00'}]})
        with connect(self.path) as c:
            c.execute("insert into payment_sources values ('example','Personal','personal','9206')")
            c.execute("insert into journals(id,business_id,date,reference,description) values(1,'example','2026-07-01','bill','Supplier invoice')")
            c.execute("insert into journal_lines values (1,1,'5000',2000,0)")
            c.execute("insert into journal_lines values (1,2,'1200',200,0)")
            c.execute("insert into journal_lines values (1,3,'2000',0,2200)")
            c.execute("insert into gst_items(journal_id,attribution_date,label,gross_cents,gst_cents,evidence,status) values(1,'2026-07-01','purchase',2200,200,'Fixture','reviewed')")
        self.req={'business_id':'example','account_id':'personal-9206','source_nickname':'Personal','confirmed_by':'user','reason':'User approved exact supplier evidence','links':[{'transaction_id':1,'journal_id':1,'amount_cents':1100}]}
    def tearDown(self): self.tmp.cleanup()
    def record(self,req=None): return supplier_links.record(self.path,req or self.req,connect,audit)
    def ids(self):
        with connect(self.path) as c:return supplier_links.linked_ids(c)
    def test_empty_status_and_dashboard_are_unchanged(self):
        with connect(self.path) as c:
            c.row_factory=sqlite3.Row
            self.assertEqual(status_report(c,'2026-07-01','2026-09-30')['unclassified_transactions'],2)
        self.assertEqual(bas_dashboard.transaction_counts(self.path,'2026-07-01','2026-09-30')['uncategorised'],2)
    def test_link_replay_and_audit_do_not_post_money(self):
        with connect(self.path) as c: before=[c.execute('select * from '+t).fetchall() for t in ('journals','journal_lines','gst_items','claim_payments','payment_matches')]
        self.assertEqual(self.record()['saved_links'],1);self.assertEqual(self.record()['saved_links'],0);self.assertEqual(self.ids(),{1})
        with connect(self.path) as c:
            after=[c.execute('select * from '+t).fetchall() for t in ('journals','journal_lines','gst_items','claim_payments','payment_matches')]
            self.assertEqual(before,after)
            self.assertEqual(c.execute("select count(*) from audit_events where action='link_supplier_evidence'").fetchone()[0],1)
            rows=proposal_store.transaction_rows(c,'2026-07-01','2026-09-30')
            self.assertEqual(rows[0][6],'Classified');self.assertEqual(rows[0][9],0)
        self.assertEqual(bas_dashboard.transaction_counts(self.path,'2026-07-01','2026-09-30')['uncategorised'],1)
    def test_grouped_purchase_and_overallocation(self):
        self.record(); q=dict(self.req,links=[{'transaction_id':2,'journal_id':1,'amount_cents':1100}]);self.record(q);self.assertEqual(self.ids(),{1,2})
        q=dict(self.req,links=[{'transaction_id':2,'journal_id':1,'amount_cents':1101}])
        with self.assertRaises(ValueError):self.record(q)
    def test_wrong_owner_business_unapproved_and_partial_rejected(self):
        for overrides in ({'confirmed_by':'assistant'},{'business_id':'wrong'},{'account_id':'company-9206'},{'source_nickname':'wrong'},{'links':[{'transaction_id':1,'journal_id':1,'amount_cents':1000}]}):
            with self.assertRaises((ValueError,KeyError)):self.record(dict(self.req,**overrides))
        self.assertEqual(self.ids(),set())
    def test_reversed_or_changed_source_reopens_row(self):
        self.record()
        with connect(self.path) as c:c.execute("update transactions set description='Changed' where id=1")
        self.assertEqual(self.ids(),set())
        with connect(self.path) as c:
            c.execute("update transactions set description='Supplier' where id=1")
            c.execute("insert into journals(business_id,date,reference,description,reverses_id) values('example','2026-07-01','rev','Reverse',1)")
        self.assertEqual(self.ids(),set())
        with self.assertRaises(ValueError):self.record()
    def test_unlink_is_audited(self):
        self.record();r=self.record(dict(self.req,action='unlink'));self.assertEqual(r['removed_links'],1);self.assertEqual(self.ids(),set())

if __name__=='__main__':unittest.main()
