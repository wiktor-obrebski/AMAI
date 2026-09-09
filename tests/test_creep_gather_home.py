"""Exercise actual gather/home JASS functions with home changes injected at Sleep.

Mocked natives verify control flow and destinations, not Warcraft movement.
"""
import unittest

from test_retreat_ownership import load_jass_function


class CreepGatherHomeTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.enemy = (10, 20), (30, 40), (50, 60)
        self.native = {'attack': self.a, 'defense': self.a}
        self.orders = []
        self.writes = []
        self.sleeps = 0
        self.on_sleep = lambda: None
        self.is_home = False
        self.env = dict(
            captain_home=self.a, captain_home_revision=0,
            major_hero=(100, 200), town_threatened=False,
            creep_captain_gather_running=False, creep_gather_max_wait=5,
            creep_gather_failed_target=None, creep_gather_failed_until=0,
            ATTACK_CAPTAIN='attack', BOTH_CAPTAINS='both', tq_timer=None,
            GetLocationX=lambda p: p[0], GetLocationY=lambda p: p[1],
            GetUnitX=lambda p: p[0], GetUnitY=lambda p: p[1],
            Location=lambda x, y: (x, y), RemoveLocation=lambda p: None,
            UnitAlive=lambda u: u is not None, CaptainGroupSize=lambda: 5,
            CaptainIsHome=lambda: self.is_home,
            SetCaptainHome=self.set_home, Sleep=self.sleep,
            CaptainGoHome=lambda: self.orders.append(self.native['attack']),
            TimerGetElapsed=lambda t: 100,
        )
        for name in ('EnsureSetCaptainHome', 'SetCaptainHomeLoc'):
            load_jass_function(self.env, 'Jobs/ARMY_TRACK.eai', name)
        load_jass_function(self.env, 'common.eai', 'GatherForCreepAttack')

    def set_home(self, captain, x, y):
        self.writes.append((captain, (x, y)))
        for name in self.native if captain == 'both' else [captain]:
            self.native[name] = (x, y)

    def sleep(self, seconds):
        self.sleeps += 1
        self.on_sleep()

    def track(self, native_target, town):
        self.env['EnsureSetCaptainHome'](native_target)
        self.env['SetCaptainHomeLoc'](town)

    def gather(self):
        result = self.env['GatherForCreepAttack']('creep')
        self.assertFalse(self.env['creep_captain_gather_running'])
        return result

    def test_unchanged_home_success_restores_attack_only(self):
        self.on_sleep = lambda: setattr(self, 'is_home', True)
        self.assertTrue(self.gather())
        self.assertEqual(self.native, dict(attack=self.a, defense=self.a))
        self.assertEqual(self.orders, [(100, 200)])
        self.assertEqual(self.env['creep_gather_failed_until'], 0)

    def test_timeout_restores_home_and_keeps_retry_backoff(self):
        self.assertFalse(self.gather())
        self.assertEqual(self.sleeps, 5)
        self.assertEqual(self.orders[-1], self.a)
        self.assertEqual(self.env['creep_gather_failed_until'], 115)

    def test_changed_home_aborts_even_if_native_reports_home(self):
        def update():
            self.track(self.b, self.b)
            self.is_home = True
        self.on_sleep = update
        self.assertFalse(self.gather())
        self.assertEqual(self.sleeps, 1)
        self.assertEqual(self.native, dict(attack=self.b, defense=self.b))
        self.assertEqual(self.orders[-1], self.b)
        self.assertEqual(self.env['creep_gather_failed_until'], 0)
        self.assertEqual(self.writes[-1], ('both', self.b))

    def test_defense_destination_survives_even_when_cached_town_differs(self):
        def update():
            self.track(self.enemy, self.b)
            self.env['town_threatened'] = True
        self.on_sleep = update
        self.assertFalse(self.gather())
        self.assertEqual(self.env['captain_home'], self.b)
        self.assertEqual(self.native, dict(attack=self.enemy, defense=self.enemy))
        self.assertEqual(self.orders[-1], self.enemy)

    def test_cached_home_refresh_without_native_write_does_not_abort(self):
        def update():
            self.track(self.a, self.a)
            self.is_home = True
        self.on_sleep = update
        self.assertTrue(self.gather())
        self.assertEqual(self.env['captain_home_revision'], 0)
        self.assertEqual(self.native['attack'], self.a)

    def test_multiple_home_changes_preserve_last_write(self):
        def update():
            self.track(self.b, self.b)
            self.track(self.a, self.a)
        self.on_sleep = update
        self.assertFalse(self.gather())
        self.assertEqual(self.env['captain_home_revision'], 2)
        self.assertEqual(self.writes[-1], ('both', self.a))

    def test_threat_without_home_write_still_restores_temporary_override(self):
        self.on_sleep = lambda: self.env.update(town_threatened=True)
        self.assertFalse(self.gather())
        self.assertEqual(self.native['attack'], self.a)
        self.assertEqual(self.env['creep_gather_failed_until'], 0)


if __name__ == '__main__':
    unittest.main()
