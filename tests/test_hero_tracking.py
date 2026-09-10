"""Source-backed diagnostics checks. No claim of Warcraft event/pathing validation."""
import re
import unittest
from pathlib import Path
from test_retreat_ownership import ROOT, function_source, load_jass_function

ORDERS = 'Diagnostics/HeroOrders.eai'
MAP = 'Diagnostics/HeroMapEvents.eai'

class HeroTrackingTests(unittest.TestCase):
    def test_order_wrappers_pass_original_arguments_once_and_return_native_result(self):
        text = (ROOT / ORDERS).read_text()
        names = re.findall(r'function (DebugHero(?:Issue\w+|UnitUseItem\w*)) takes', text)
        self.assertEqual(len(names), 11)
        for name in names:
            source = function_source(ORDERS, name)
            args = source.split(' takes ')[1].split(' returns ')[0].split(', ')
            values = [dict(unit='hero', string='move', integer=851986, real=17.5,
                           location='loc', widget='target', item='item')[a.split()[0]] for a in args[:-1]]
            for enabled, is_hero in [(False, True), (True, False), (True, True)]:
                for result in (True, False):
                    calls, markers, after = [], [], []
                    def before(*args):
                        markers.append(args)
                        return 42
                    env = dict(debug_hero_tracking=enabled, UNIT_TYPE_HERO='hero',
                               IsUnitType=lambda *a: is_hero,
                               DebugHeroOrderBefore=before,
                               DebugHeroOrderAfter=lambda *a: after.append(a),
                               OrderId=lambda s: 851986, GetHandleId=lambda v: 99,
                               GetLocationX=lambda v: 10, GetLocationY=lambda v: 20,
                               GetWidgetX=lambda v: 30, GetWidgetY=lambda v: 40,
                               GetItemTypeId=lambda v: 100)
                    env[name.removeprefix('DebugHero')] = lambda *a: (calls.append(a), result)[1]
                    load_jass_function(env, ORDERS, name)
                    with self.subTest(name=name, enabled=enabled, hero=is_hero, result=result):
                        self.assertIs(env[name](*values, 'test:source'), result)
                        self.assertEqual(calls, [tuple(values)])
                        self.assertEqual(len(markers), int(enabled and is_hero))
                        self.assertEqual(after, [(values[0], 42 if enabled and is_hero else 0, result)])

    def test_ai_logging_uses_ai_safe_conversion_and_reaches_formation_native(self):
        for name in ['HeroOrders.eai', 'HeroSnapshots.eai']:
            self.assertNotRegex((ROOT / 'Diagnostics' / name).read_text(), r'\bI2S\s*\(')
        calls, records = [], []
        def unavailable_i2s(value):
            raise AssertionError('I2S is unavailable in the AI VM')
        env = dict(debug_hero_tracking=True, debug_hero_cache=None,
            debug_hero_index=0, debug_hero_dirty=False, tq_timer='timer',
            I2S=unavailable_i2s, Int2Str=str, R2I=int, GetAiPlayer=lambda:1,
            TimerGetElapsed=lambda t:130.187,
            InitGameCache=lambda name:(calls.append(('cache',name)), 'cache')[1],
            FlushStoredMission=lambda *a:calls.append(('flush',*a)),
            StoreString=lambda *a:records.append(a),
            StoreInteger=lambda *a:calls.append(('count',*a)),
            InitAssault=lambda:calls.append(('assault',)))
        load_jass_function(env, ORDERS, 'DebugHeroLog')
        load_jass_function(env, ORDERS, 'DebugHeroInitAssault')
        env['DebugHeroInitAssault']('FormGroupAM')
        env['DebugHeroInitAssault']('FormGroupAM')
        self.assertEqual(calls.count(('cache','AMAI_HeroTrace_P1.w3v')), 1)
        self.assertEqual(calls.count(('assault',)), 2)
        self.assertEqual([r[:3] for r in records], [('cache','P1','L0'),('cache','P1','L1')])
        self.assertTrue(all(r[3].startswith('tms=130187 HERO CONTROL:') for r in records))
        self.assertEqual(env['debug_hero_index'], 2)
        self.assertTrue(env['debug_hero_dirty'])

    def test_add_assault_keeps_boolean_return(self):
        for result in (True, False):
            calls=[]
            env=dict(debug_hero_tracking=True, Int2Str=str, DebugHeroLog=lambda s: None,
                     AddAssault=lambda *a: (calls.append(a), result)[1])
            load_jass_function(env, ORDERS, 'DebugHeroAddAssault')
            self.assertIs(env['DebugHeroAddAssault'](3, 100, 'source'), result)
            self.assertEqual(calls, [(3,100)])

    def test_event_observer_records_unmatched_orders_without_inventing_source(self):
        for event, kind, target in [('immediate','immediate',None), ('point','point',None), ('target','target','target')]:
            logs=[]
            env=dict(amai_hero_event_tracking=True, GetTriggerUnit=lambda:'hero',
                UNIT_TYPE_HERO='hero', IsUnitType=lambda *a:True,
                GetTriggerEventId=lambda:event, EVENT_PLAYER_UNIT_ISSUED_POINT_ORDER='point',
                EVENT_PLAYER_UNIT_ISSUED_TARGET_ORDER='target', GetOrderPointX=lambda:17,
                GetOrderPointY=lambda:18, GetOrderTarget=lambda:target,
                GetOrderTargetUnit=lambda:target, GetWidgetX=lambda u:27, GetWidgetY=lambda u:28,
                GetPlayerId=lambda u:1, GetOwningPlayer=lambda u:'player', GetIssuedOrderId=lambda:851983,
                GetHandleId=lambda u:0 if u is None else (123 if u=='hero' else 456),
                GetUnitTypeId=lambda u:0 if u is None else 100, GetUnitX=lambda u:7,
                GetUnitY=lambda u:8, GetUnitState=lambda *a:300, UNIT_STATE_LIFE='hp',
                I2S=str, R2I=int, AMAIHeroEventLog=lambda p,s:logs.append((p,s)))
            load_jass_function(env, MAP, 'AMAIHeroOrderEvent')
            env['AMAIHeroOrderEvent']()
            self.assertEqual(len(logs),1)
            self.assertIn('kind='+kind, logs[0][1])
            self.assertIn('order=851983', logs[0][1])
            self.assertNotIn('native', logs[0][1].lower())
            self.assertIn('target='+('456' if target else '0'), logs[0][1])

    def test_snapshot_counts_support_excluding_self_and_hidden_enemies(self):
        units={'hero','friend','locked','ally','enemy','unseen','worker','building','dead'}
        owners=dict.fromkeys(units,'ai'); owners.update(ally='ally',enemy='enemy',unseen='enemy')
        logs=[]
        env=dict(CreateGroup=set, GroupEnumUnitsInRange=lambda g,*a:g.update(units),
            FirstOfGroup=lambda g:next(iter(g),None), GroupRemoveUnit=lambda g,u:g.remove(u),
            DestroyGroup=lambda g:None, UnitAlive=lambda u:u!='dead',
            IsUnitHidden=lambda u:False, IsUnitLoaded=lambda u:False,
            IsUnitType=lambda u,t:(u=='worker' and t=='peon') or (u=='building' and t=='structure'),
            UNIT_TYPE_STRUCTURE='structure', UNIT_TYPE_PEON='peon', UNIT_STATE_MAX_LIFE='max',
            GetUnitState=lambda *a:100, GetOwningPlayer=lambda u:owners[u], ai_player='ai',
            GetUnitStrength=lambda u:2, IsStandardUnit=lambda u:u!='locked', IsUnitBuying=lambda u:False,
            IsPlayerAlly=lambda p,a:p=='ally', IsPlayerEnemy=lambda p,a:p=='enemy',
            IsUnitVisible=lambda u,p:u!='unseen', IsUnitInvisible=lambda u,p:False,
            GetUnitX=lambda u:10, GetUnitY=lambda u:20, main_army=-1,
            DebugHeroLog=logs.append, DebugHeroState=lambda u:' hero=123',
            Int2Str=str,R2I=int,B2S=lambda x:str(x).lower(),GetHandleId=lambda u:123,
            IsUnitIllusion=lambda u:False,GetArmyOfUnit=lambda u:0,CaptainGroupSize=lambda:5,
            CaptainInCombat=lambda x:False,town_threatened=False,TownThreatened=lambda:False,
            air_strength=77,no_sleep=True,own_strength=88,ally_strength_sum=99,enemy_strength_sum=111)
        load_jass_function(env, 'Diagnostics/HeroSnapshots.eai', 'DebugHeroSnapshot')
        env['DebugHeroSnapshot']('hero')
        support=logs[-1]
        for expected in ['ownCount=2','own=4','readyCount=1','ready=2','ally=2','visibleEnemyCount=1','visibleEnemy=2']:
            self.assertIn(expected,support)
        self.assertEqual([env[k] for k in ['air_strength','no_sleep','own_strength','ally_strength_sum','enemy_strength_sum']], [77,True,88,99,111])

    def test_diagnostics_do_not_write_gameplay_globals_or_issue_orders_outside_wrappers(self):
        for path in (ROOT/'Diagnostics').glob('*.eai'):
            text=path.read_text()
            locals_=set(re.findall(r'\blocal \w+ (\w+)',text))
            for var in re.findall(r'^\s*set (\w+)',text,re.M):
                self.assertTrue(var in locals_ or var.startswith(('debug_hero_','amai_hero_')), (path,var))
            if path.name!='HeroOrders.eai':
                self.assertNotRegex(text,r'\b(?:Issue\w+|UnitUseItem\w*|CaptainGoHome|CaptainAttack|RemoveGuardPosition|RecycleGuardPosition)\(')
            self.assertNotRegex(text,r'\b(?:GetOwnStrength|GetOwnAttackStrength|GetRandomInt|GetRandomReal|GetTargetStrength|Select\w+)\(')

    def test_ai_diagnostic_variables_do_not_shadow_declared_globals(self):
        common = (ROOT / 'common.eai').read_text()
        globals_text = common.split('globals', 1)[1].split('endglobals', 1)[0]
        globals_ = set(re.findall(r'^\s*(?:constant\s+)?(?:integer|real|boolean|string|unit|group|location|player|timer|trigger|gamecache|hashtable|widget|item|code|effect|ability|texttag)\s+(?:array\s+)?(\w+)(?=\s|$)', globals_text, re.M))
        self.assertIn('hero', globals_)
        for file in ['HeroOrders.eai', 'HeroSnapshots.eai']:
            source = (ROOT / 'Diagnostics' / file).read_text()
            for name, args, body in re.findall(r'function (\w+) takes (.*?) returns \w+\n(.*?)endfunction', source, re.S):
                declared = set(re.findall(r'local \w+ (\w+)', body))
                declared.update(arg.split()[-1] for arg in args.split(', ') if arg != 'nothing')
                self.assertFalse(declared & globals_, (file, name, declared & globals_))

    def test_raw_order_writer_coverage(self):
        names=re.findall(r'function DebugHero((?:Issue\w+|UnitUseItem\w*|RecycleGuardPosition|RemoveGuardPosition|CaptainGoHome|CaptainAttack|SetCaptainHome|AddAssault|InitAssault)) takes', (ROOT/ORDERS).read_text())
        pattern=r'\b(?:'+'|'.join(names)+r')\('
        for path in [ROOT/'common.eai',ROOT/'races.eai',*sorted((ROOT/'Jobs').glob('*.eai'))]:
            active='\n'.join(s.split('//')[0] for s in path.read_text().splitlines())
            self.assertNotRegex(active,pattern,str(path))

if __name__=='__main__':
    unittest.main()
