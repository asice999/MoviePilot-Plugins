import os, sys, unittest
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(__file__))
from episode_gap import calculate_missing_episodes
from onestrm_backfill import build_season_record, mark_attempt, should_attempt

class OneSrmEngineTests(unittest.TestCase):
    def test_middle_gap_is_exact(self):
        self.assertEqual(calculate_missing_episodes(20, list(range(1, 15)) + list(range(16, 21))), [15])
    def test_all_missing_returns_every_episode(self):
        self.assertEqual(calculate_missing_episodes(3, []), [1, 2, 3])
    def test_future_episodes_are_excluded(self):
        self.assertEqual(calculate_missing_episodes(5, [1], [1, 2, 3]), [2, 3])
    def test_subscription_does_not_hide_middle_gap(self):
        r = build_season_record(223911, '仙逆', 1, 160, list(range(1, 15)) + list(range(16, 161)), list(range(1, 161)), subscription_id=28)
        self.assertEqual(r['missing_episodes'], [15]); self.assertEqual(r['season_state'], 'missing')
    def test_whole_aired_season_is_backfill_needed(self):
        r = build_season_record(1, '整季缺失', 2, 4, [], [1, 2, 3, 4])
        self.assertEqual(r['missing_episodes'], [1, 2, 3, 4]); self.assertEqual(r['season_state'], 'backfill_needed')
    def test_success_stays_queued_until_library_confirms(self):
        now = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)
        q = mark_attempt(build_season_record(3, '缺一集', 1, 3, [1, 3], [1, 2, 3]), True, now)
        r = build_season_record(3, '缺一集', 1, 3, [1, 3], [1, 2, 3], previous=q, now=now + timedelta(hours=1))
        self.assertEqual(r['season_state'], 'queued'); self.assertFalse(should_attempt(r, now + timedelta(hours=23), 24)); self.assertTrue(should_attempt(r, now + timedelta(hours=25), 24))
    def test_failure_waits_for_retry_window(self):
        now = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)
        f = mark_attempt(build_season_record(4, '没资源', 1, 2, [1], [1, 2]), False, now, 'no resource')
        self.assertEqual(f['season_state'], 'failed'); self.assertEqual(f['attempt_count'], 1); self.assertFalse(should_attempt(f, now + timedelta(hours=23), 24)); self.assertTrue(should_attempt(f, now + timedelta(hours=24), 24))

if __name__ == '__main__': unittest.main()
