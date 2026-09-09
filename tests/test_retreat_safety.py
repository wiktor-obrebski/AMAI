"""Exercise retreat rescue, recovery and reset coordination with mocked natives."""
import unittest
import test_retreat_ownership as ownership
from test_retreat_ownership import load_jass_function


class RetreatSafetyTests(unittest.TestCase):
    def setUp(self):
        ownership.RetreatOwnershipTests.setUp(self)
        self.tp = []
        self.hp = 100
        self.distance = 3000
        self.enemy = 5
        self.healed = False
        self.channel = False
        self.env.update(
            hero_unit={1: 'hero'}, teleporting=False, tp_item=1,
            flee_health_percentage=0.4, flee_minimum_health=150,
            GetUnitState=lambda u, s: self.hp if s == 'life' else 1000,
            IsRetreatTeleporting=lambda u: self.channel,
            GetUnitLoc=lambda u: self.distance, RMax=max,
            GetUnitX=lambda u: 0, GetUnitY=lambda u: 0,
            GetLocationNonCreepStrength=lambda *a: self.enemy,
            GetItemNumberOnUnit=lambda *a: 1,
            TryRetreatHealingItem=lambda *a: self.healed,
            TeleportHome=lambda hn: self.tp.append(hn),
        )
        self.env['in_retreat_group'].add('hero')
        load_jass_function(self.env, 'Jobs/MICRO_HERO.eai', 'RescueRetreatHero')

    def test_critical_owned_hero_can_teleport_without_releasing_ownership(self):
        self.env['RescueRetreatHero'](1)
        self.assertEqual(self.tp, [1])
        self.assertTrue(self.env['IsRetreatOrderLocked']('hero'))
        self.assertEqual(self.recycled, [])

    def test_rescue_does_not_override_channel_or_other_teleport(self):
        self.channel = True
        self.env['RescueRetreatHero'](1)
        self.channel = False
        self.env['teleporting'] = True
        self.env['RescueRetreatHero'](1)
        self.assertEqual(self.tp, [])

    def test_rescue_avoids_unnecessary_tp(self):
        for hp, distance, enemy, healed in (
            (900, 3000, 5, False), (100, 500, 5, False),
            (100, 3000, 0, False), (100, 3000, 5, True),
        ):
            self.hp, self.distance, self.enemy, self.healed = hp, distance, enemy, healed
            self.env['RescueRetreatHero'](1)
        self.assertEqual(self.tp, [])

    def test_rescue_does_not_command_unlocked_or_dead_hero(self):
        self.dead.add('hero')
        self.env['RescueRetreatHero'](1)
        self.dead.clear()
        self.env['in_retreat_group'].clear()
        self.env['RescueRetreatHero'](1)
        self.assertEqual(self.tp, [])

    def pending(self):
        self.env['in_retreat_group'].clear()
        self.env['retreat_reset_pending'].add('hero')
        self.distance = 0

    def test_reset_waits_for_tp_even_after_global_retreat_ends(self):
        self.pending()
        self.channel = True
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(self.jobs, [(1, 'retreat', 0, 'hero')])
        self.assertEqual(self.recycled, [])

    def test_new_home_returns_pending_unit_to_travel(self):
        self.pending()
        self.distance = 1000
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(self.jobs, [(0, 'send_home', 1, 'hero')])
        self.assertIn('hero', self.env['in_retreat_group'])
        self.assertNotIn('hero', self.env['retreat_reset_pending'])
        self.assertEqual(self.recycled, [])

    def test_recovery_item_gets_time_before_another_attempt(self):
        self.pending()
        self.env['isfleeing'] = True
        self.env['RetreatRecovery'] = lambda u: True
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(self.jobs, [(15, 'retreat', 0, 'hero')])
        self.assertEqual(self.recycled, [])

    def test_no_healing_resource_does_not_prevent_release(self):
        self.pending()
        self.env['RetreatRecovery'] = lambda u: False
        self.env['ResetRetreatJob']('hero')
        self.assertFalse(self.env['IsRetreatOrderLocked']('hero'))
        self.assertEqual(self.recycled, ['hero'])

    def test_send_home_preserves_tp_instead_of_moving_or_holding(self):
        self.channel = True
        load_jass_function(self.env, 'Jobs/SEND_HOME.eai', 'SendUnitHomeJob')
        self.env['SendUnitHomeJob']('hero', 1)
        self.assertEqual(self.jobs, [(1, 'send_home', 1, 'hero')])
        self.assertIn('hero', self.env['in_retreat_group'])

    def test_recovery_does_not_issue_orders_in_combat_or_during_tp(self):
        self.pending()
        load_jass_function(self.env, 'common.eai', 'RetreatRecovery')
        self.env['TryRetreatHealingItem'] = lambda *a: self.fail('healing in unsafe state')
        self.assertFalse(self.env['RetreatRecovery']('hero'))
        self.enemy = 0
        self.channel = True
        self.assertFalse(self.env['RetreatRecovery']('hero'))

    def test_recovery_uses_well_without_moving_patient(self):
        self.pending()
        self.enemy = 0
        orders = []
        self.env.update(
            race_has_moonwells=True, ai_player=1, racial_farm=2, old_id={2: 'well'},
            UNIT_STATE_MANA='mana', CreateGroup=set,
            GroupEnumUnitsInRange=lambda g, *a: g.add('well'),
            FirstOfGroup=lambda g: next(iter(g), None), DestroyGroup=lambda g: g.clear(),
            GetOwningPlayer=lambda u: 1, GetUnitTypeId=lambda u: u,
            IssueTargetOrder=lambda *a: orders.append(a),
        )
        load_jass_function(self.env, 'common.eai', 'RetreatRecovery')
        self.assertFalse(self.env['RetreatRecovery']('hero'))
        self.assertEqual(orders, [('well', 'replenish', 'hero')])

    def test_tp_detection_ignores_other_inventory_orders(self):
        self.env.update(GetUnitCurrentOrder=lambda u: 852008, OrderId=lambda s: 999,
                        UnitItemInSlot=lambda u, i: 'item', old_id={1: 'tp'},
                        GetItemTypeId=lambda it: 'potion')
        load_jass_function(self.env, 'common.eai', 'IsRetreatTeleporting')
        self.assertFalse(self.env['IsRetreatTeleporting']('hero'))
        self.env['GetItemTypeId'] = lambda it: 'tp'
        self.assertTrue(self.env['IsRetreatTeleporting']('hero'))


if __name__ == '__main__':
    unittest.main()
