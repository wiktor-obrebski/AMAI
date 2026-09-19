"""Execute control wrappers against natives with immediate and delayed effects."""
import re
import subprocess
import unittest
from test_retreat_ownership import ROOT, load_jass_function

PATH = 'Diagnostics/HeroOrders.eai'

class ControlTrackingTests(unittest.TestCase):
    def environment(self, enabled=True):
        records, calls = [], []
        orders = {'hero1':851972, 'hero2':851972, 'extra':851972}
        env = dict(debug_hero_tracking=enabled, debug_hero_control_call=0,
            debug_attack_sequence=0, debug_attack_operation=7, debug_attack_command=2,
            hero_unit={1:'hero1',2:None,3:'hero2'}, Int2Str=str, R2I=int, B2S=str,
            attack_running=False, isfleeing=True, canflee=True, break_attack=True,
            retreat_controlled=True, CaptainGroupSize=lambda:3, CaptainRetreating=lambda:False,
            DebugHeroLog=records.append, UNIT_TYPE_HERO='hero',
            IsUnitType=lambda u,t:u in orders, GetHandleId=lambda u:99,
            GetUnitX=lambda u:100, GetUnitY=lambda u:200,
            DebugHeroState=lambda u:' hero='+u+' current='+str(orders[u])+' retreat=true pending=false')
        return env,records,calls,orders

    def test_all_control_wrappers_preserve_calls_arguments_and_results(self):
        cases = [('RemoveGuardPosition',['hero1']),('RecycleGuardPosition',['hero1']),
            ('CaptainGoHome',[]),('CaptainAttack',[17.5,-22.5]),
            ('SetCaptainHome',[2,17.5,-22.5]),('InitAssault',[]),
            ('AddAssault',[1,123]),('AttackMoveKill',['target']),
            ('AttackMoveXY',[17,-22]),('ClearCaptainTargets',[])]
        for enabled in (False,True):
            for name,args in cases:
                for result in (False,True):
                    with self.subTest(enabled=enabled,name=name,result=result):
                        env,logs,calls,orders=self.environment(enabled)
                        def native(*args):
                            calls.append(args)
                            orders['hero1']=851983
                            return result
                        env[name]=native
                        load_jass_function(env,PATH,'DebugHero'+name)
                        actual=env['DebugHero'+name](*args,'test:source')
                        self.assertEqual(calls,[tuple(args)])
                        if name=='AddAssault': self.assertIs(actual,result)
                        if not enabled:
                            self.assertEqual(logs,[])
                            self.assertEqual(env['debug_hero_control_call'],0)
                            continue
                        self.assertEqual(env['debug_hero_control_call'],1)
                        self.assertTrue(any('phase=BEFORE call=1 source=test:source action='+name in s for s in logs))
                        self.assertTrue(any('phase=AFTER call=1' in s for s in logs))
                        before=[s for s in logs if s.startswith('HERO CONTROL STATE:') and 'phase=BEFORE' in s]
                        after=[s for s in logs if s.startswith('HERO CONTROL STATE:') and 'phase=AFTER' in s]
                        self.assertEqual(len(before),2)
                        self.assertEqual(len(after),2)
                        self.assertIn('hero=hero1 current=851972',before[0])
                        self.assertIn('hero=hero1 current=851983',after[0])
                        self.assertIn('retreat=true pending=false',after[0])
                        if name=='AddAssault': self.assertIn('accepted='+str(result),logs[-1])

    def test_guard_focus_outside_roster_is_recorded_once_and_nonheroes_skip(self):
        for focus,expected in [('hero1',2),('extra',3),('worker',0),(None,0)]:
            env,logs,calls,orders=self.environment()
            env['RecycleGuardPosition']=calls.append
            load_jass_function(env,PATH,'DebugHeroRecycleGuardPosition')
            env['DebugHeroRecycleGuardPosition'](focus,'test')
            self.assertEqual(calls,[focus])
            self.assertEqual(len([s for s in logs if 'HERO CONTROL STATE:' in s]),expected*2)

    def test_delayed_effect_is_not_reported_as_synchronous(self):
        env,logs,calls,orders=self.environment()
        env['CaptainGoHome']=lambda:calls.append('home')
        load_jass_function(env,PATH,'DebugHeroCaptainGoHome')
        env['DebugHeroCaptainGoHome']('first')
        recorded=list(logs)
        orders['hero1']=851983
        self.assertEqual(logs,recorded)
        self.assertFalse(any('current=851983' in s for s in logs))
        env['DebugHeroCaptainGoHome']('second')
        self.assertTrue(any('phase=BEFORE call=2 source=second' in s for s in logs))
        self.assertTrue(any('call=2 phase=BEFORE hero=hero1 current=851983' in s for s in logs))

    def test_gameplay_sources_outside_diagnostics_are_byte_identical_to_master(self):
        base='8705227687e1d8b1207f9c12a62ea2ed4b29dc17'
        paths=subprocess.check_output(['git','ls-tree','-r','--name-only',base],cwd=ROOT,text=True).splitlines()
        for path in paths:
            if path.endswith('.eai') and not path.startswith('Diagnostics/'):
                expected=subprocess.check_output(['git','show',base+':'+path],cwd=ROOT)
                self.assertEqual((ROOT/path).read_bytes(),expected,path)

    def test_control_helpers_have_no_sleep_order_or_gameplay_mutation(self):
        from test_retreat_ownership import function_source
        for name in ('DebugHeroControlBefore','DebugHeroControlSample','DebugHeroControlAfter'):
            source=function_source(PATH,name)
            self.assertNotRegex(source,r'\b(?:Sleep|TriggerSleepAction|Issue\w+|Group\w+|StartThread)\(')
            locals_=set(re.findall(r'local \w+ (\w+)',source))
            self.assertTrue(set(re.findall(r'^\s*set (\w+)',source,re.M)) <= locals_|{'debug_hero_control_call'})
