"""Exercise actual SEND_HOME scheduling with mocked inventory/shop natives."""
import unittest
from test_retreat_ownership import load_jass_function


class HeroHealingTests(unittest.TestCase):
    def setUp(self):
        self.hp = 268
        self.item = False
        self.purchase_ok = True
        self.transfer_ok = True
        self.donor = None
        self.locked = False
        self.jobs, self.orders, self.used = [], [], []
        def purchase(*args):
            self.item = self.purchase_ok
            return self.purchase_ok
        def transfer(*args):
            self.item = self.transfer_ok
            return self.transfer_ok
        def use(*args):
            self.used.append(args)
            return True
        self.env = dict(
            UNIT_STATE_LIFE='hp', UNIT_STATE_MAX_LIFE='max', UNIT_STATE_MANA='mana',
            UNIT_TYPE_HERO='hero', GetUnitState=lambda u,s: {'hp':self.hp,'max':850,'mana':200}[s],
            IsRetreatOrderLocked=lambda u:self.locked, IsUnitType=lambda *a:True,
            GetHeroHealingItem=lambda:1, GetHeroManaItem=lambda:0,
            SomeUnitHasHealingItem=lambda *a:self.donor,
            buy_type={1:3}, BT_RACIAL_ITEM=3, racial_shop=2, old_id={1:101,2:102},
            GetUnitOfTypeNearUnit=lambda *a:'shop', UpdateRecoveryHome=lambda:None,
            GetUnitCurrentOrder=lambda u:0, OrderId=lambda s:99, I2R=float,
            GetItemNumberOnUnit=lambda *a:int(self.item), GetSlotsFreeOnUnit=lambda u:1,
            DistanceBetweenUnits=lambda *a:100, buy_distance=300, ai_player='ai',
            IssueImmediateOrder=lambda *a:self.orders.append(a),
            IssueNeutralImmediateOrderById=purchase, UnitAddItem=transfer,
            GetItemOfTypeOnUnit=lambda *a:'potion', GetItemInstantType=lambda i:0,
            ITEMTYPE_CONTINUOUS=1, UnitUseItem=use, UnitUseItemTarget=use,
            GetItemHealingTime=lambda i:10, Max=max,
            TQAddUnitJob=lambda *a:self.jobs.append(a), SEND_HOME='heal', RESET_GUARD_POSITION='reset',
            IsUnitInGroup=lambda u,g:u in g, debug_retreat_transit_group=set())
        load_jass_function(self.env,'Jobs/SEND_HOME.eai','SendUnitHomeJob')

    def tick(self):
        self.env['SendUnitHomeJob']('mk',0)

    def test_purchase_then_use_then_release_only_after_health_recovers(self):
        self.tick()
        self.assertEqual(self.jobs,[(4,'heal',0,'mk')])
        self.tick()
        self.assertTrue(self.used)
        self.assertEqual(self.jobs[-1],(10,'heal',0,'mk'))
        self.hp = 510
        self.tick()
        self.assertEqual(self.jobs[-1],(2,'reset',0,'mk'))

    def test_failed_purchase_retries_without_releasing_and_natural_healing_exits(self):
        self.purchase_ok = False
        for _ in range(3):
            self.tick()
        self.assertEqual(self.jobs,[(4,'heal',0,'mk')]*3)
        self.hp = 510
        self.tick()
        self.assertEqual(self.jobs[-1],(2,'reset',0,'mk'))

    def test_transfer_success_or_failure_does_not_release_low_health_hero(self):
        self.donor = 'other'
        for succeeds in [False,True]:
            self.transfer_ok = succeeds
            self.tick()
            self.assertEqual(self.jobs[-1],(2,'heal',0,'mk'))
        self.tick()
        self.assertTrue(self.used)

    def test_retreat_preempts_queued_normal_healing(self):
        self.locked = True
        self.tick()
        self.assertEqual(self.jobs,[])
        self.assertEqual(self.orders,[])

    def test_dead_hero_does_not_retry_shop(self):
        self.hp = 0
        self.tick()
        self.assertEqual(self.jobs,[(2,'reset',0,'mk')])
        self.assertEqual(self.orders,[])
