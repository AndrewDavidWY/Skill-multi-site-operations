import copy
from datetime import date
import json
from pathlib import Path
import unittest
from check_daily_snapshot import check, timestamp


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]/'assets'
        self.config = json.loads((root/'sites.example.json').read_text())
        self.snapshots = json.loads((root/'snapshots.example.json').read_text())
        self.now = timestamp('2026-01-15T12:00:00Z')
        self.day = date(2026, 1, 12)

    def result(self):
        return check(self.config,self.snapshots,self.day,self.now)

    def test_zero_is_preserved_and_no_cross_site_sum(self):
        r = self.result()
        self.assertTrue(r['all_ready'])
        self.assertEqual(r['sites'][1]['values']['activeUsers'], 0)
        self.assertIsNone(r['cross_site_totals'])

    def test_unknown_or_missing_data_mode_rejected(self):
        for value in (None, 'live', {}, []):
            self.snapshots['data_mode'] = value
            with self.assertRaises(ValueError):
                self.result()
        self.snapshots.pop('data_mode')
        with self.assertRaises(ValueError):
            self.result()

    def test_data_mode_is_preserved_without_verifying_measurement(self):
        for mode in ('demo', 'real_snapshot'):
            self.snapshots['data_mode'] = mode
            r = self.result()
            self.assertEqual(r['data_mode'], mode)
            self.assertFalse(r['measurement_and_business_validity_verified'])

    def test_missing_site_does_not_become_zero(self):
        self.snapshots['records'].pop()
        r = self.result()['sites'][1]
        self.assertEqual(r['status'], 'missing')
        self.assertIsNone(r['values']['activeUsers'])

    def test_wrong_property_suppresses_values(self):
        self.snapshots['records'][0]['query']['property_id'] = '999999999'
        r = self.result()['sites'][0]
        self.assertEqual(r['status'], 'quality_limited')
        self.assertIsNone(r['values']['activeUsers'])

    def test_old_fetch_remains_stale(self):
        self.snapshots['records'][0]['fetched_at'] = '2026-01-13T10:00:00Z'
        self.assertEqual(self.result()['sites'][0]['status'], 'stale')

    def test_missing_metric_stays_null(self):
        del self.snapshots['records'][0]['values']['activeUsers']
        r = self.result()['sites'][0]
        self.assertIsNone(r['values']['activeUsers'])
        self.assertEqual(r['status'], 'quality_limited')

    def test_thresholding_cannot_look_ready(self):
        self.snapshots['records'][0]['quality']['subjectToThresholding'] = True
        self.assertEqual(self.result()['sites'][0]['status'], 'quality_limited')

    def test_processing_window_is_site_timezone_aware(self):
        self.now = timestamp('2026-01-14T20:00:00Z')
        for row in self.snapshots['records']:
            row['fetched_at'] = '2026-01-14T19:00:00Z'
        r = self.result()['sites']
        self.assertEqual(r[0]['status'], 'ready')
        self.assertEqual(r[1]['status'], 'provisional')

    def test_early_snapshot_does_not_mature_without_refetch(self):
        for row in self.snapshots['records']:
            row['fetched_at'] = '2026-01-14T12:00:00Z'
        r = self.result()
        self.assertFalse(r['all_ready'])
        for row in r['sites']:
            self.assertEqual(row['status'], 'provisional')
            self.assertIn('refetch_required_after_processing_window', row['flags'])
            self.assertTrue(row['current_processing_window_elapsed'])
            self.assertFalse(row['processing_window_elapsed_at_fetch'])

    def test_duplicate_day_rejected(self):
        self.snapshots['records'].append(copy.deepcopy(self.snapshots['records'][0]))
        with self.assertRaises(ValueError):
            self.result()

    def test_future_timestamp_rejected(self):
        self.snapshots['records'][0]['fetched_at'] = '2026-01-16T00:00:00Z'
        with self.assertRaises(ValueError):
            self.result()

    def test_nonfinite_and_boolean_metrics_rejected(self):
        for value in (float('nan'), float('inf'), True):
            self.snapshots['records'][0]['values']['activeUsers'] = value
            with self.assertRaises(ValueError):
                self.result()

    def test_manual_quality_unknown_remains_visible(self):
        row = self.snapshots['records'][0]
        row.update(method='manual_export', quality_metadata_available=None)
        self.assertIn('quality_metadata_unknown', self.result()['sites'][0]['flags'])

    def test_failed_attempt_is_not_a_successful_fetch(self):
        self.snapshots['records'][0] = {'site_id':'alpha','report_date':'2026-01-12','status':'error','attempted_at':'2026-01-15T08:00:00Z','error_reason':'synthetic denial'}
        r = self.result()['sites'][0]
        self.assertEqual(r['status'],'error')
        self.assertNotIn('fetched_at',r)
        self.assertIsNone(r['values']['activeUsers'])

    def test_error_cannot_contain_zero_values(self):
        self.snapshots['records'][0].update(status='error', error_reason='synthetic denial', attempted_at='2026-01-15T08:00:00Z')
        with self.assertRaises(ValueError):
            self.result()


if __name__ == '__main__':
    unittest.main()
