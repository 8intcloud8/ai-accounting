import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'accounting_core'))
import case_tracker as tracker
import memory_store as memory


class CaseTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = dict(entity='demo', goal='bas', start='2026-07-01', end='2026-09-30')
        self.fact = dict(entity='demo', topic='supplier.example.business_use', value=90,
                         status='user_confirmed', effective_from='2026-07-01', source='test user', reason='initial', expected_id=None)
    def tearDown(self): self.temp.cleanup()
    def complete(self, case, step):
        f=self.root/(step+'.txt');f.write_text('verified example evidence')
        return tracker.record(self.root,case,dict(step=step,status='done',note='checked',evidence=[f.name],expected_revision=tracker.status(self.root,case)['revision']))
    def test_resume_and_entity_isolation(self):
        c=tracker.start(self.root,self.request)['case']['id']
        self.assertEqual(c,tracker.start(self.root,self.request)['case']['id'])
        memory.save(self.root,self.fact)
        self.assertEqual(90,tracker.status(self.root,c)['facts_at_start'][0]['value'])
        self.assertEqual([],memory.read(self.root,'another','2026-07-01')['facts'])
    def test_correction_dates_and_stale_revision(self):
        first=memory.save(self.root,self.fact)['saved_id']
        memory.save(self.root,dict(self.fact,value=100,effective_from='2026-08-01',expected_id=first))
        self.assertEqual(90,memory.read(self.root,'demo','2026-07-31')['facts'][0]['value'])
        self.assertEqual(100,memory.read(self.root,'demo','2026-08-01')['facts'][0]['value'])
        with self.assertRaises(ValueError):memory.save(self.root,self.fact)
    def test_memory_invalidates_review(self):
        c=tracker.start(self.root,self.request)['case']['id'];self.complete(c,'intake')
        memory.save(self.root,self.fact)
        self.assertEqual('stale',tracker.status(self.root,c)['steps'][0]['status'])
    def test_dependencies_evidence_and_independent_work(self):
        c=tracker.start(self.root,self.request)['case']['id']
        with self.assertRaises(ValueError):self.complete(c,'draft')
        tracker.record(self.root,c,dict(step='intake',status='blocked',note='missing facts'))
        self.assertIn('statements',[r['step'] for r in tracker.status(self.root,c)['next']])
        self.complete(c,'documents');self.complete(c,'invoices')
        (self.root/'documents.txt').write_text('changed')
        states={r['step']:r['status'] for r in tracker.status(self.root,c)['steps']}
        self.assertEqual('stale',states['documents']);self.assertEqual('stale',states['invoices'])
    def test_concurrent_fact_change_rejects_completion(self):
        c=tracker.start(self.root,self.request)['case']['id']
        revision=tracker.status(self.root,c)['revision']
        (self.root/'intake.txt').write_text('prior result')
        memory.save(self.root,self.fact)
        with self.assertRaises(ValueError):
            tracker.record(self.root,c,dict(step='intake',status='done',note='old result',evidence=['intake.txt'],expected_revision=revision))
    def test_invalid_inputs_and_symlinks(self):
        with self.assertRaises(ValueError):memory.save(self.root,[])
        (self.root/'db').symlink_to('/tmp',target_is_directory=True)
        with self.assertRaises(ValueError):memory.save(self.root,self.fact)
    def test_read_normalization(self):
        memory.save(self.root,self.fact)
        self.assertEqual(1,len(memory.read(self.root,' demo ','2026-07-01',topic=' supplier.example.business_use ')['facts']))
    def test_expired_and_withdrawn_do_not_revive(self):
        first=memory.save(self.root,self.fact)['saved_id']
        second=memory.save(self.root,dict(self.fact,value=100,effective_from='2026-08-01',effective_to='2026-09-01',expected_id=first))['saved_id']
        self.assertEqual([],memory.read(self.root,'demo','2026-09-01')['facts'])
        memory.save(self.root,dict(self.fact,status='withdrawn',effective_from='2026-10-01',expected_id=second))
        self.assertEqual([],memory.read(self.root,'demo','2026-10-02')['facts'])

if __name__=='__main__':unittest.main()
