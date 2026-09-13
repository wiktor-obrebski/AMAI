"""Tracking passthrough and gameplay-preservation checks; no engine emulation."""
import re
import subprocess
import unittest
from test_retreat_ownership import ROOT, load_jass_function

PATH = 'Diagnostics/HeroOrders.eai'

class AttackTrackingTests(unittest.TestCase):
    def environment(self, enabled):
        calls, logs = [], []
        env = dict(debug_hero_tracking=enabled, debug_attack_sequence=0,
            debug_attack_operation=0, debug_attack_command=0,
            DebugHeroLog=logs.append, Int2Str=str, R2I=int, B2S=str,
            attack_running=True, break_attack=False, isfleeing=True, canflee=True,
            retreat_controlled=True, CaptainRetreating=lambda:False,
            GetHandleId=lambda u:123, GetUnitX=lambda u:10, GetUnitY=lambda u:20,
            AttackMoveKill=lambda *a:calls.append(('unit',a)),
            AttackMoveXY=lambda *a:calls.append(('point',a)),
            ClearCaptainTargets=lambda:calls.append(('clear',())),
            IsUnitType=lambda *a:True, UNIT_TYPE_HERO=1,
            DebugHeroState=lambda u:' hero=123 retreat=true pending=false fleeing=true')
        for name in ['DebugHeroAttackState','DebugHeroAttackBegin','DebugHeroAttackEnd',
                     'DebugHeroAttackMoveKill','DebugHeroAttackMoveXY',
                     'DebugHeroClearCaptainTargets','DebugHeroRetreatMembership']:
            load_jass_function(env,PATH,name)
        return env,calls,logs

    def test_commands_pass_arguments_once_with_logging_on_and_off(self):
        for enabled in [False,True]:
            env,calls,logs=self.environment(enabled)
            env['DebugHeroAttackMoveKill']('target','test')
            env['DebugHeroAttackMoveXY'](12,-34,'test')
            env['DebugHeroClearCaptainTargets']('test')
            self.assertEqual(calls,[('unit',('target',)),('point',(12,-34)),('clear',())])
            self.assertEqual(env['debug_attack_command'],2 if enabled else 0)
            if enabled:
                self.assertTrue(any('CLEAR_TARGETS_CALL' in s for s in logs))
                self.assertTrue(any('fleeing=True' in s for s in logs))
            else:self.assertEqual(logs,[])

    def test_nested_operations_restore_parent_and_membership_is_logged(self):
        env,calls,logs=self.environment(True)
        outer=env['DebugHeroAttackBegin']('outer')
        inner=env['DebugHeroAttackBegin']('inner')
        self.assertNotEqual(outer,inner)
        env['DebugHeroAttackEnd'](inner,outer,'inner')
        self.assertEqual(env['debug_attack_operation'],outer)
        env['DebugHeroAttackEnd'](outer,0,'outer')
        self.assertEqual(env['debug_attack_operation'],0)
        env['DebugHeroRetreatMembership']('hero','capture')
        self.assertIn('retreat=true pending=false fleeing=true',logs[-1])
        self.assertEqual(calls,[])

    def test_gameplay_statements_and_arguments_are_unchanged(self):
        def normalize(s):
            lines=[]
            for line in s.splitlines():
                line=line.split('//',1)[0].strip()
                if not line:continue
                if re.match(r'(local integer debug_(parent_operation|operation)|set debug_operation =|call DebugHero(Attack(Begin|End|State)|RetreatMembership))',line):continue
                line=re.sub(r'call DebugHeroAttackMoveKill\((.*), "[^"]*"\)',r'call AttackMoveKill(\1)',line)
                line=re.sub(r'call DebugHeroAttackMoveXY\((.*), "[^"]*"\)',r'call AttackMoveXY(\1)',line)
                line=re.sub(r'call DebugHeroClearCaptainTargets\("[^"]*"\)', 'call ClearCaptainTargets()',line)
                lines.append(line)
            return lines
        for path in ['common.eai','Jobs/RETREAT_CONTROL.eai','Jobs/RESET_RETREAT.eai',
                     'Jobs/SEND_HOME.eai','Jobs/TELEPORT.eai','Jobs/MICRO_HERO.eai']:
            base=subprocess.check_output(['git','show','404a07a:'+path],cwd=ROOT,text=True)
            self.assertEqual(normalize(base),normalize((ROOT/path).read_text()),path)
