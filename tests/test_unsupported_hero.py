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
        self.env = dict(hero_unit={1:'hero'}, hero_isolation_checks={1:0}, teleporting=False,
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
            self.env['hero_isolation_checks'][1]=1
            if kind=='home': self.distance=500
            if kind=='healing': self.unready.add('hero')
            if kind=='shopping': self.buying.add('hero')
            if kind=='transport': self.loaded.add('hero')
            if kind=='dead': self.dead.add('hero')
            if kind=='tp': self.env['teleporting']=True
            self.assertFalse(self.tick())
            self.assertEqual(self.env['hero_isolation_checks'][1],0)
            self.assertEqual(self.jobs,[])

    def test_job_preserves_emergency_rescue_and_shopping_does_not_force_assault(self):
        micro=function_source('Jobs/MICRO_HERO.eai','MicroHeroJob')
        self.assertLess(micro.index('call SaveHero(hn'),micro.index('if RetreatUnsupportedHero(hn)'))
        self.assertLess(micro.index('if RetreatUnsupportedHero(hn)'),micro.index('if armyOfHero >= 0 and not teleporting'))
        self.assertNotIn('AddAssault',function_source('Jobs/BUY_ITEM.eai','BuyItemJob'))
