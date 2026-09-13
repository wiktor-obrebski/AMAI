"""Actual JASS hero danger check, with controlled local unit observations."""
import unittest
from test_retreat_ownership import load_jass_function, function_source


class UnsupportedHeroTests(unittest.TestCase):
    def setUp(self):
        self.units = ['hero', 'enemy']
        self.owner = {'hero':'ai', 'enemy':'enemy'}
        self.strength = {'hero':8, 'enemy':36}
        self.hidden, self.loaded, self.dead, self.invisible = set(), set(), set(), set()
        self.unready, self.buying, self.towers, self.workers = set(), set(), set(), set()
        self.visible = {'enemy'}
        self.distance = 4000
        self.jobs, self.removed, self.destroyed = [], [], []
        self.locked = set()
        self.env = dict(hero_unit={1:'hero'}, hero_isolation_seen={1:False}, teleporting=False,
            UnitAlive=lambda u:u not in self.dead, IsRetreatTeleporting=lambda u:False,
            IsStandardUnit=lambda u:u not in self.unready and u not in self.locked,
            IsUnitBuying=lambda u:u in self.buying, IsUnitLoaded=lambda u:u in self.loaded,
            IsUnitHidden=lambda u:u in self.hidden,
            GetUnitLoc=lambda u:0, GetRecoveryHome=lambda:0,
            DistanceBetweenPoints_dk=lambda *a:self.distance,
            GetUnitStrength=lambda u:self.strength[u], CreateGroup=list,
            GroupEnumUnitsInRange=lambda g,*a:g.extend(self.units),
            GetUnitX=lambda u:0, GetUnitY=lambda u:0,
            FirstOfGroup=lambda g:g[0] if g else None,
            GroupRemoveUnit=lambda g,u:g.remove(u), DestroyGroup=self.destroyed.append,
            UNIT_STATE_MAX_LIFE='max', GetUnitState=lambda *a:675,
            UNIT_TYPE_PEON='worker', UNIT_TYPE_STRUCTURE='structure',
            IsUnitType=lambda u,t:u in (self.workers if t=='worker' else self.towers),
            IsUnitTower=lambda u:u in self.towers,
            IsPlayerAlly=lambda a,b:b in ['ai','ally'], ai_player='ai',
            GetOwningPlayer=lambda u:self.owner[u], Player=lambda p:p,
            PLAYER_NEUTRAL_AGGRESSIVE='creeps', IsPlayerEnemy=lambda a,b:b not in ['ai','ally'],
            IsUnitVisible=lambda u,p:u in self.visible, IsUnitInvisible=lambda u,p:u in self.invisible,
            in_retreat_group=self.locked, GroupAddUnit=lambda g,u:g.add(u),
            RemoveGuardPosition=self.removed.append, TQAddUnitJob=lambda *a:self.jobs.append(a), SEND_HOME='home')
        load_jass_function(self.env,'Jobs/MICRO_HERO.eai','RetreatUnsupportedHero')

    def tick(self):
        return self.env['RetreatUnsupportedHero'](1)

    def add_support(self, name, strength=3, owner='ai'):
        self.units.append(name)
        self.strength[name] = strength
        self.owner[name] = owner

    def test_full_health_isolated_hero_withdraws_after_two_observations(self):
        self.assertFalse(self.tick())
        self.assertTrue(self.tick())
        self.assertEqual(self.jobs,[(0,'home',1,'hero')])
        self.assertEqual(self.removed,['hero'])
        self.assertEqual(self.locked,{'hero'})
        self.assertFalse(self.tick())
        self.assertEqual(len(self.jobs),1)
        self.assertEqual(len(self.destroyed),2)

    def test_naga_with_one_support_against_17_strength(self):
        self.add_support('troop')
        self.strength['enemy'] = 17
        self.assertFalse(self.tick())
        self.assertTrue(self.tick())

    def test_brief_danger_does_not_accumulate_across_safe_sample(self):
        self.tick()
        self.visible.clear()
        self.assertFalse(self.tick())
        self.visible.add('enemy')
        self.assertFalse(self.tick())
        self.assertEqual(self.jobs,[])

    def test_creeps_and_unseen_enemies_do_not_trigger(self):
        for mode in ['creeps','unseen','invisible']:
            self.setUp()
            if mode=='creeps': self.owner['enemy']='creeps'
            if mode=='unseen': self.visible.clear()
            if mode=='invisible': self.invisible.add('enemy')
            self.tick()
            self.assertFalse(self.tick())

    def test_supported_army_and_tower_defense_are_not_treated_as_isolation(self):
        for kind in ['army','tower','ally']:
            self.setUp()
            if kind=='army':
                for i in range(3): self.add_support(str(i))
            else:
                self.add_support('support',30,'ally' if kind=='ally' else 'ai')
                if kind=='tower': self.towers.add('support')
            self.tick()
            self.assertFalse(self.tick())

    def test_pending_distant_or_loaded_reinforcements_are_not_support(self):
        for kind in ['pending','loaded','distant']:
            self.setUp()
            self.add_support('troop',50)
            if kind=='pending': self.unready.add('troop')
            if kind=='loaded': self.loaded.add('troop')
            if kind=='distant': self.units.remove('troop')
            self.tick()
            self.assertTrue(self.tick())

    def test_local_recovery_defense_and_other_ownership_are_preserved(self):
        for kind in ['home','healing','shopping','transport','dead','tp']:
            self.setUp()
            self.env['hero_isolation_seen'][1]=True
            if kind=='home': self.distance=500
            if kind=='healing': self.unready.add('hero')
            if kind=='shopping': self.buying.add('hero')
            if kind=='transport': self.loaded.add('hero')
            if kind=='dead': self.dead.add('hero')
            if kind=='tp': self.env['teleporting']=True
            self.assertFalse(self.tick())
            self.assertEqual(self.env['hero_isolation_seen'][1],False)
            self.assertEqual(self.jobs,[])

    def test_job_preserves_emergency_rescue(self):
        micro=function_source('Jobs/MICRO_HERO.eai','MicroHeroJob')
        self.assertLess(micro.index('call SaveHero(hn'),micro.index('if RetreatUnsupportedHero(hn)'))
        self.assertLess(micro.index('if RetreatUnsupportedHero(hn)'),micro.index('if armyOfHero >= 0 and not teleporting'))

    def test_withdraw_arrive_release_without_global_retreat_or_duplicate_capture(self):
        pending, recycled, moves = set(), [], []
        self.env.update(
            IsRetreatOrderLocked=lambda u:u in self.locked or u in pending,
            IsUnitInGroup=lambda u,g:u in g, retreat_reset_pending=pending,
            debug_retreat_transit_group=set(), UpdateRecoveryHome=lambda:None,
            UNIT_STATE_LIFE='life', UNIT_TYPE_HERO='hero',
            IsUnitType=lambda u,t:t=='hero', GetHeroHealingItem=lambda:0,
            GetHeroManaItem=lambda:0, RetreatRecovery=lambda u:False,
            SendHomeMoveUnitToLoc=lambda u,l:moves.append(u),
            IssueImmediateOrder=lambda *a:True, RESET_RETREAT='reset_retreat',
            RESET_GUARD_POSITION='reset_guard',
            GroupRemoveUnit=lambda g,u:g.discard(u) if isinstance(g,set) else g.remove(u),
            RecycleGuardPositionAM=recycled.append,
            unit_healing=set(), unit_rescueing=set(), unit_harassing=set(), unit_zepplin_move=set(),
            isfleeing=False, retreat_controlled=False, attack_running=True)
        for path,name in [('Jobs/RESET_GUARD_POSITION.eai','ResetGuardPositionJob'),
                          ('Jobs/RESET_RETREAT.eai','ResetRetreatJob'),
                          ('Jobs/SEND_HOME.eai','SendUnitHomeJob')]:
            load_jass_function(self.env,path,name)
        self.tick()
        self.assertTrue(self.tick())
        self.assertEqual(self.jobs.pop(),(0,'home',1,'hero'))
        self.env['SendUnitHomeJob']('hero',1)
        self.assertEqual(moves,['hero'])
        self.assertEqual(self.jobs.pop(),(4,'home',1,'hero'))
        self.assertFalse(self.tick())
        self.env['ResetGuardPositionJob']('hero')  # stale job cannot release traveller
        self.assertEqual(recycled,[])
        self.distance=0
        self.env['SendUnitHomeJob']('hero',1)
        self.assertEqual(self.locked,set())
        self.assertEqual(pending,{'hero'})
        self.assertEqual(self.jobs.pop(),(15,'reset_retreat',0,'hero'))
        self.env['ResetGuardPositionJob']('hero')  # same protection after arrival
        self.assertEqual(recycled,[])
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(pending,set())
        self.assertEqual(recycled,['hero'])
        self.assertFalse(self.env['isfleeing'])
        self.assertFalse(self.env['retreat_controlled'])
        self.assertTrue(self.env['attack_running'])
        self.assertEqual(self.jobs,[])
