import os, tempfile, unittest
import common

class IdentityPartitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=common.DATA
        common.DATA=self.tmp.name;os.makedirs(common.DATA,exist_ok=True)
    def tearDown(self):
        common.DATA=self.old;self.tmp.cleanup()
    def test_legacy_plus_shards_are_read_without_growing_legacy(self):
        fields=["event_id","outcome_id"]
        common.append_rows("line_identity_history",[{"event_id":"legacy","outcome_id":"1"}],fields)
        legacy_size=os.path.getsize(common.csv_path("line_identity_history"))
        common.append_partitioned_rows("line_identity_history",[{"event_id":"new","outcome_id":"2"}],fields,"2026-10-20")
        self.assertEqual(os.path.getsize(common.csv_path("line_identity_history")),legacy_size)
        self.assertEqual({r["event_id"] for r in common.read_partitioned_rows("line_identity_history")},{"legacy","new"})

if __name__=="__main__":
    unittest.main()
