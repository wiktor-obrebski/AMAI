"""Exercise the actual retreat controller with a native state change at Sleep.

Mocks cover scheduling and ownership, not engine pathing or combat outcomes.
"""
import unittest
from test_retreat_ownership import ROOT, function_source, load_jass_function

PATH = 'Jobs/RETREAT_CONTROL.eai'

class NativeRetreatTests(unittest.TestCase):
    def environment(self, retreat_during_sleep=True):
        jobs, unit_jobs, guards, flee_calls = [], [], [], []
        env = dict(debug_hero_tracking=False, debug_retreat_run_seq=0,
            debug_retreat_epoch=0, debug_retreat_transit_active=False,
            canflee=True, isfleeing=False, retreat_controlled=True,
            retreat_end_switch=True, break_attack=False, attack_running=True,
            main_hero_home_tp_retreat_pending=False, native_retreat=False,
            CaptainRetreating=lambda:env['native_retreat'], CaptainIsHome=lambda:False,
            major_hero='hero', UnitAlive=lambda u:True, UpdateRecoveryHome=lambda:None,
            DebugHeroAttackState=lambda *a:None, DebugStartRetreatTransitTracking=lambda:None,
            DebugTraceRetreatTransitState=lambda *a:None,
            town_threatened=False, town_threat_break=True, player_defeated=False,
            debug_flee_candidate_group=set(), main_army=0, army_loc=[1], army_strength=[8],
            ai_player='own', battle_radius=1500, creep_battle_radius=750,
            CreateGroup=set, GroupClear=lambda g:g.clear(),
            GroupEnumUnitsInRange=lambda g,*a:g.add('enemy'),
            GroupEnumUnitsOfPlayer=lambda g,*a:g.add('hero'),
            SelectUnittype=lambda g,*a:g, SelectByHidden=lambda g,*a:g,
            SelectByAlive=lambda g,*a:g, GetLocationX=lambda p:1, GetLocationY=lambda p:1,
            MoveLocation=lambda *a:None, last_enemy_loc=1, enemy_loc=1,
            last_ally_loc=1, ally_loc=1, FirstOfGroup=lambda g:next(iter(g),None),
            GetUnitStrength=lambda u:19, ModuloInteger=lambda a,b:a%b,
            Sleep=lambda t:env.update(native_retreat=retreat_during_sleep),
            GetOwningPlayer=lambda u:'enemy', Player=lambda p:'neutral',
            PLAYER_NEUTRAL_AGGRESSIVE=12, IsPlayerAlly=lambda *a:False,
            IsPlayerEnemy=lambda *a:True, IsUnitInvisibleAM=lambda *a:False,
            GetUnitX=lambda u:1, GetUnitY=lambda u:1, GroupRemoveUnit=lambda g,u:g.remove(u),
            DestroyGroup=lambda g:None, ancient_expanding=False, br_rush_attacked=False,
            I2R=float, Max=max, ordinary_creep_attack_running=False, Trace=lambda s:None,
            Real2Str=str, CaptainInCombat=lambda b:False, desperation_assault=False,
            SetGroupsFlee=flee_calls.append, sleep_multiplier=1, RETREAT_CONTROL='retreat',
            TQAddJob=lambda *a:jobs.append(a), in_retreat_group=set(),retreat_reset_pending=set(),
            IsUnitInGroup=lambda u,g:u in g, IsStandardUnit=lambda u:True,
            IsUnitType=lambda *a:False, UNIT_TYPE_STRUCTURE='structure',UNIT_TYPE_PEON='peon',
            GetUnitCurrentOrder=lambda u:0, OrderId=lambda s:1,
            DebugHeroRemoveGuardPosition=lambda u,*a:guards.append(u),
            DebugHeroRetreatMembership=lambda *a:None,GroupAddUnit=lambda g,u:g.add(u),
            TQAddUnitJob=lambda *a:unit_jobs.append(a), SEND_HOME='home',
            GetUnitLoc=lambda u:1,GetRecoveryHome=lambda:2,DistanceBetweenPoints=lambda *a:1000)
        load_jass_function(env,PATH,'LatchNativeRetreat')
        load_jass_function(env,PATH,'RetreatControlJob')
        return env,jobs,unit_jobs,guards,flee_calls

    def test_retreat_starting_during_evaluation_commits_then_captures(self):
        env,jobs,unit_jobs,guards,flee_calls=self.environment()
        env['RetreatControlJob']()
        self.assertTrue(env['isfleeing'])
        self.assertTrue(env['break_attack'])
        self.assertFalse(env['retreat_end_switch'])
        self.assertEqual(jobs,[(0,'retreat',0)])
        self.assertEqual(flee_calls,[]) # No cancellation of native retreat.
        env['RetreatControlJob']()
        self.assertEqual(guards,['hero'])
        self.assertEqual(env['in_retreat_group'],{'hero'})
        self.assertEqual(unit_jobs,[(0,'home',1,'hero')])
        self.assertEqual(flee_calls,[True])

    def test_no_native_retreat_keeps_existing_cancel_path(self):
        env,jobs,_,_,flee_calls=self.environment(False)
        env['RetreatControlJob']()
        self.assertFalse(env['isfleeing'])
        self.assertFalse(env['break_attack'])
        self.assertFalse(env['canflee'])
        self.assertEqual(flee_calls,[False])
        self.assertEqual(jobs,[(2,'retreat',0)])

    def test_latch_preserves_permission_tp_and_existing_retreat_guards(self):
        for controlled,allowed,home,pending,native,already,expected in [
            (True,True,False,False,True,False,True),
            (True,True,True,False,False,False,True),
            (True,True,True,True,False,False,False),
            (True,True,True,True,True,False,True),
            (False,True,False,False,True,False,False),
            (True,False,False,False,True,False,False),
            (True,True,False,False,True,True,False)]:
            with self.subTest(controlled=controlled,allowed=allowed,home=home,pending=pending,native=native,already=already):
                env,*_=self.environment()
                env.update(retreat_controlled=controlled,canflee=allowed,
                    CaptainIsHome=lambda:home,main_hero_home_tp_retreat_pending=pending,
                    native_retreat=native,isfleeing=already)
                self.assertEqual(env['LatchNativeRetreat'](),expected)
                self.assertEqual(env['break_attack'],expected)
                self.assertEqual(env['retreat_end_switch'],not expected)

    def test_attack_rechecks_cancellation_before_post_sleep_recruitment(self):
        source=function_source('common.eai','CommonSleepUntilTargetDeadAM')
        tail=source.split('call StaggerSleep(1 * sleep_multiplier, (1 * sleep_multiplier) + 2)',1)[1]
        statements=[line.strip() for line in tail.splitlines() if line.strip() and not line.strip().startswith('//')]
        self.assertEqual(statements[0],'exitwhen (break_attack or isfleeing) and not desperation_assault')

class QuietDiagnosticsTests(unittest.TestCase):
    def test_disabled_helpers_do_not_allocate_scan_or_write(self):
        for path,name in [('common.eai','DebugTraceAttackFormationState'),
                          ('common.eai','DebugTraceTownDefense'),
                          (PATH,'DebugStartRetreatTransitTracking'),
                          (PATH,'DebugTraceRetreatTransitState'),
                          ('common.eai','TraceLog'),('common.eai','TraceLogInit'),
                          ('common.eai','TraceLogFlush'),
                          ('Diagnostics/HeroMapEvents.eai','InitAMAIHeroEvents')]:
            with self.subTest(name=name):
                env=dict(debug_hero_tracking=False,amai_hero_event_tracking=False)
                load_jass_function(env,path,name)
                # Any native call/lookup would fail: only disabled flags are supplied.
                env[name](*(['test'] if 'takes string' in function_source(path,name) else []))

    def test_trace_arguments_are_gated_and_defaults_are_quiet(self):
        for path in ROOT.rglob('*.eai'):
            lines=path.read_text().splitlines()
            for i,line in enumerate(lines):
                if line.strip().startswith('call TraceAll('):
                    self.assertEqual(lines[i-1].strip(),'if debug_hero_tracking then',str(path))
        self.assertIn('boolean debug_hero_tracking = false',(ROOT/'Diagnostics/HeroTraceGlobals.eai').read_text())
        self.assertIn('boolean amai_hero_event_tracking = false',(ROOT/'Diagnostics/HeroMapGlobals.eai').read_text())
