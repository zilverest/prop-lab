"""Regression checks for Git-safe, lossless change-only line history."""
import csv
import os
import tempfile
import unittest
from unittest.mock import patch

import common
import maintenance
import snapshot


class TestLinePartitions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_data=common.DATA
        common.DATA=self.tmp.name
        # maintenance imported DATA via from common import *
        self.old_maintenance_data=maintenance.DATA
        maintenance.DATA=self.tmp.name

    def tearDown(self):
        common.DATA=self.old_data
        maintenance.DATA=self.old_maintenance_data
        self.tmp.cleanup()

    def test_migration_preserves_rows_and_is_idempotent(self):
        fields=snapshot.LINE_FIELDS
        p=common.csv_path("lines")
        with open(p,"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields)
            w.writeheader()
            for date in ("2026-10-20","2026-10-20","2026-10-26"):
                w.writerow(dict.fromkeys(fields,"",ts=date+"T12:00:00Z",event_id=date))
        out=maintenance.compact_lines()
        self.assertEqual(out["rows"],3)
        self.assertEqual(out["kept"],3)
        self.assertEqual(out["partitions"],2)
        self.assertFalse(os.path.exists(p))
        self.assertEqual(len(common.read_partitioned_rows("lines")),3)
        self.assertEqual(maintenance.compact_lines()["mode"],"partitioned")

    def test_new_snapshots_append_to_daily_partition(self):
        fields=snapshot.LINE_FIELDS
        row=dict.fromkeys(fields,"")
        row.update(ts="2026-11-04T13:00:00Z",event_id="test")
        self.assertEqual(common.append_partitioned_rows("lines",[row],fields,"2026-11-04"),1)
        self.assertFalse(os.path.exists(common.csv_path("lines")))
        self.assertEqual(len(common.read_partitioned_rows("lines")),1)

    def test_conflict_does_not_delete_legacy_archive(self):
        fields=snapshot.LINE_FIELDS
        p=common.csv_path("lines")
        with open(p,"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            w.writerow(dict.fromkeys(fields,"",ts="2026-10-20T12:00:00Z"))
        os.makedirs(os.path.join(self.tmp.name,"lines"),exist_ok=True)
        open(os.path.join(self.tmp.name,"lines","2026-10-20.csv"),"w").close()
        with self.assertRaises(RuntimeError):
            maintenance.compact_lines()
        self.assertTrue(os.path.exists(p))


if __name__=="__main__":
    unittest.main()
