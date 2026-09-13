"""Execute regroup ownership, planning and movement with mocked game state."""
import unittest
from test_retreat_ownership import load_jass_function, function_source


class HeroRegroupTests(unittest.TestCase):
    def setUp(self):
        self.pos={'hero':0,'second':0,'troop1':3000,'troop2':3100,'enemy':3000}
        self.units=['hero','second','troop1','troop2']
        self.dead=set()
        self.illusions=set()
        self.orders=[]
        self.recycled=[]
        self.threat=False
        self.strength={'hero':8,'second':8,'troop1':5,'troop2':5,'enemy':20}
        def remove(g,u):
            if isinstance(g,set):g.discard(u)
            else:g.remove(u)
        self.env=dict(hero_unit={1:'hero',2:'second',3:None},
            hero_regroup=set(),in_retreat_group=set(),retreat_reset_pending=set(),
            unit_healing=set(),unit_rescueing=set(),unit_harassing=set(),unit_zepplin_move=set(),
            UnitAlive=lambda u:u is not None and u not in self.dead,
            IsUnitInGroup=lambda u,g:u in g,GroupAddUnit=lambda g,u:g.add(u),GroupRemoveUnit=remove,
            RemoveGuardPosition=lambda u:None,RecycleGuardPosition=self.recycled.append,
            IssueImmediateOrder=lambda u,o:self.orders.append((u,o)),
            IssuePointOrderLoc=lambda u,o,l:self.orders.append((u,o,l)),
            recovery_home=0,home_location=0,GetRecoveryHome=lambda:0,UpdateRecoveryHome=lambda:None,
            IsUnitInRangeLoc=lambda u,l,r:abs(self.pos[u]-l)<=r,
            GetUnitLoc=lambda u:self.pos[u],RemoveLocation=lambda l:None,
            isfleeing=False,canflee=False,attack_running=False,town_threatened=False,
            TownThreatened=lambda:self.threat,teleporting=False,IsRetreatTeleporting=lambda u:False,
            main_army=0,army_loc={0:3000},
            CreateGroup=list,GroupEnumUnitsInRangeOfLoc=lambda g,l,r,f:g.extend(u for u in self.units if abs(self.pos[u]-l)<=r),
            FirstOfGroup=lambda g:g[0] if g else None,DestroyGroup=lambda g:None,
            IsUnitHidden=lambda u:False,IsUnitLoaded=lambda u:False,
            IsUnitIllusion=lambda u:u in self.illusions,
            UNIT_TYPE_PEON='peon',UNIT_TYPE_STRUCTURE='structure',UNIT_TYPE_HERO='hero',UNIT_TYPE_SUMMONED='summon',
            IsUnitType=lambda u,t:t=='hero' and u in ['hero','second'],
            UNIT_STATE_MAX_LIFE='max',GetUnitState=lambda *a:100,
            GetOwningPlayer=lambda u:'enemy' if u=='enemy' else 'ai',ai_player='ai',
            IsUnitBuying=lambda u:False,GetUnitStrength=lambda u:self.strength[u],IsUnitTower=lambda u:False,
            IsPlayerEnemy=lambda a,b:b=='enemy',Player=lambda p:p,PLAYER_NEUTRAL_AGGRESSIVE='creep',
            IsUnitVisible=lambda *a:True,IsUnitInvisible=lambda *a:False)
        for name in ['IsRetreatOrderLocked','RecycleGuardPositionAM','IsHeroStagedForFormation','IsStandardUnit','IsRetreatUnavailableForAttack']:
            load_jass_function(self.env,'common.eai',name)
        for name in ['ReturnUnitToArmy','ReleaseRegroupHero','ReleaseStagedHeroes','CanHeroJoinGroup','UpdateHeroRegroup']:
            load_jass_function(self.env,'HeroRegroup.eai',name)
        load_jass_function(self.env,'Jobs/RESET_GUARD_POSITION.eai','ResetGuardPositionJob')

    def hold(self,u='hero'):
        self.env['ReturnUnitToArmy'](u)

    def tick(self):
        self.env['UpdateHeroRegroup']('hero')

    def test_reset_hands_off_without_native_release_and_stale_resets_cannot_release(self):
        self.env['unit_healing'].add('hero')
        self.env['ResetGuardPositionJob']('hero')
        self.assertIn('hero',self.env['hero_regroup'])
        self.assertNotIn('hero',self.env['unit_healing'])
        self.env['ResetGuardPositionJob']('hero')
        self.env['RecycleGuardPositionAM']('hero')
        self.assertEqual(self.recycled,[])
        self.assertFalse(self.env['IsStandardUnit']('hero'))

    def test_staged_heroes_count_for_planning_and_release_together_at_formation(self):
        self.hold();self.hold('second')
        self.assertFalse(self.env['IsRetreatUnavailableForAttack']('hero'))
        self.assertTrue(self.env['IsRetreatOrderLocked']('hero'))
        self.env['ReleaseStagedHeroes']()
        self.assertEqual(self.recycled,['hero','second'])
        self.assertEqual(self.env['hero_regroup'],set())

    def test_active_formation_does_not_release_separated_hero(self):
        self.hold();self.env['attack_running']=True
        self.env['ReleaseStagedHeroes']()
        self.assertEqual(self.recycled,[])
        self.assertTrue(self.env['IsRetreatUnavailableForAttack']('hero'))

    def test_moves_to_actual_friendly_group_then_releases_on_arrival(self):
        self.hold();self.env['attack_running']=True
        self.tick()
        self.assertEqual(self.orders[-1],('hero','move',3000))
        self.assertEqual(self.recycled,[])
        self.pos['hero']=3000
        self.tick()
        self.assertEqual(self.recycled,['hero'])

    def test_missing_dead_or_recovering_group_is_not_a_rendezvous(self):
        for mode in ['missing','dead','pending']:
            self.setUp();self.hold();self.env['attack_running']=True
            if mode=='missing':self.env['army_loc'][0]=None
            if mode=='dead':self.dead.update(['troop1','troop2'])
            if mode=='pending':self.env['retreat_reset_pending'].update(['troop1','troop2'])
            self.tick()
            self.assertEqual(self.orders[-1],('hero','holdposition'))
            self.assertEqual(self.recycled,[])

    def test_enemy_at_rendezvous_or_on_trip_returns_to_recovery(self):
        for location in [3000,1400]:
            self.setUp();self.hold();self.env['attack_running']=True
            self.pos['hero']=1400;self.pos['enemy']=location;self.units.append('enemy')
            self.tick()
            self.assertEqual(self.orders[-1],('hero','move',0))
            self.assertEqual(self.recycled,[])

    def test_only_supported_local_defense_can_release(self):
        self.hold();self.threat=True
        self.env['ReleaseStagedHeroes']()
        self.tick()
        self.assertEqual(self.recycled,[])
        self.pos.update(troop1=0,troop2=100,enemy=0)
        self.units.append('enemy');self.strength['enemy']=5
        self.tick()
        self.assertEqual(self.recycled,['hero'])

    def test_flee_teleport_and_death(self):
        self.hold();self.env['attack_running']=True;self.env['isfleeing']=True
        self.pos['hero']=1800
        self.tick();self.assertEqual(self.orders[-1],('hero','move',0))
        self.env['teleporting']=True;before=list(self.orders)
        self.tick();self.assertEqual(self.orders,before)
        self.dead.add('hero');self.tick()
        self.assertEqual(self.env['hero_regroup'],set())
        self.assertEqual(self.recycled,[])

    def test_source_wiring_has_no_sleep_between_staged_release_and_formation(self):
        form=function_source('common.eai','FormGroupAM')
        between=form.split('call ReleaseStagedHeroes()',1)[1].split('call DebugHeroInitAssault',1)[0]
        self.assertNotIn('call Sleep',between)
        buy=function_source('Jobs/BUY_ITEM.eai','BuyItemJob')
        self.assertNotIn('call RecycleGuardPositionAM',buy)
        self.assertEqual(buy.count('if IsStandardUnit(shop_sent) then'),2)

    def test_native_formation_cannot_recruit_regroup_owned_hero_type(self):
        assaults=[]
        self.env.update(GetUnitTypeId=lambda u:'HERO' if u=='hero' else 'OTHER',
                        AddAssault=lambda *a:assaults.append(a))
        load_jass_function(self.env,'common.eai','AddAssaultAvailable')
        self.hold()
        self.env['AddAssaultAvailable'](60,'HERO','test')
        self.assertEqual(assaults,[])
        self.env['AddAssaultAvailable'](5,'FOOTMAN','test')
        self.assertEqual(assaults,[(5,'FOOTMAN')])
        self.env['ReleaseStagedHeroes']()
        self.env['AddAssaultAvailable'](1,'HERO','test')
        self.assertEqual(assaults[-1],(1,'HERO'))

    def test_handoff_does_not_interrupt_teleport_and_staged_hero_can_anchor_planning(self):
        self.env['IsRetreatTeleporting']=lambda u:True
        self.hold()
        self.assertEqual(self.orders,[])
        self.tick()
        self.assertEqual(self.orders,[])
        self.env['IsRetreatTeleporting']=lambda u:False
        self.env.update(hero_built={1:True,2:False,3:False})
        load_jass_function(self.env,'common.eai','GetMajorHero')
        self.assertEqual(self.env['GetMajorHero'](None),'hero')

    def test_shopping_completion_cannot_take_hero_from_another_active_job(self):
        for owner in ['unit_healing','unit_rescueing','unit_harassing','unit_zepplin_move']:
            self.setUp()
            self.env[owner].add('hero')
            self.hold()
            self.assertEqual(self.env['hero_regroup'],set())
            self.assertEqual(self.orders,[])
            self.assertEqual(self.recycled,[])

    def test_approach_does_not_stop_before_support_is_in_range(self):
        self.hold();self.env['attack_running']=True
        self.pos.update(hero=2700,troop1=3700,troop2=3720)
        self.tick()
        self.assertEqual(self.orders[-1],('hero','move',3000))
        self.assertEqual(self.recycled,[])
        self.pos['hero']=3000
        self.tick()
        self.assertEqual(self.recycled,['hero'])

    def test_illusions_cannot_supply_a_ready_army(self):
        self.hold();self.env['attack_running']=True
        self.illusions.update(['troop1','troop2'])
        self.tick()
        self.assertEqual(self.orders[-1],('hero','holdposition'))
        self.assertEqual(self.recycled,[])
