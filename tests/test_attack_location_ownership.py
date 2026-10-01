"""Run distance helpers with strict location lifetimes, including the attack callsites."""
import math
import re
import unittest
from test_retreat_ownership import function_source, load_jass_function

class AttackLocationOwnershipTests(unittest.TestCase):
    def environment(self):
        live = {}
        removed = []
        next_id = 0
        def location(x,y):
            nonlocal next_id
            next_id += 1
            live[next_id] = (x,y)
            return next_id
        def remove(handle):
            self.assertIn(handle,live,'Location removed twice')
            del live[handle]
            removed.append(handle)
        env=dict(Location=location,RemoveLocation=remove,
            GetLocationX=lambda h:live[h][0],GetLocationY=lambda h:live[h][1],
            SquareRoot=math.sqrt)
        for name in ['GetSubtractionLoc','GetSubtractionLoc_dd','GetLengthOfLoc_d',
                     'DistanceBetweenPoints','DistanceBetweenPoints_dd']:
            load_jass_function(env,'common.eai',name)
        return env,live,removed

    def test_attack_progress_preserves_borrowed_army_location(self):
        source=function_source('common.eai','CommonSleepUntilTargetDeadAM')
        calls=re.findall(r'set (cur_dist|gen_cur_dist) = (\w+)\(army_loc\[main_army\], target_loc\)\s+call RemoveLocation\(target_loc\)',source)
        self.assertEqual({name for name,_ in calls},{'cur_dist','gen_cur_dist'})
        for name,helper in calls:
            with self.subTest(branch=name):
                env,live,removed=self.environment()
                army=env['Location'](0,0)
                target=env['Location'](3,4)
                self.assertEqual(env[helper](army,target),5)
                env['RemoveLocation'](target)
                self.assertEqual(live,{army:(0,0)})
                self.assertEqual(removed.count(target),1)

    def test_old_consuming_helper_invalidates_borrowed_location(self):
        env,live,_=self.environment()
        army=env['Location'](0,0)
        target=env['Location'](3,4)
        self.assertEqual(env['DistanceBetweenPoints_dd'](army,target),5)
        self.assertNotIn(army,live)
        with self.assertRaisesRegex(AssertionError,'Location removed twice'):
            env['RemoveLocation'](target)
