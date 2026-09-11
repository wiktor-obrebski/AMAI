"""Execute recovery selection and integration with mocked natives, not pathfinding."""
import re
import unittest
from test_retreat_ownership import ROOT, load_jass_function, function_source


class RecoveryHomeTests(unittest.TestCase):
    def setUp(self):
        self.units = ['main', 'expo']
        self.pos = {'main': (0, 0), 'expo': (7300, 0)}
        self.danger = {'main': 0, 'expo': 0}
        self.dead = set()
        self.owner = dict.fromkeys(self.units, 'ai')
        self.clock = 0
        self.destroyed = []
        def strength(x, y, radius):
            self.env['air_strength'] = 999
            return self.danger[next(u for u in self.pos if self.pos[u] == (x,y))]
        self.env = dict(recovery_home=None, recovery_anchor=None, recovery_next_check=0,
            home_location=[0,0], captain_home=[7300,0], ai_player='ai', air_strength=42,
            tq_timer='timer', TimerGetElapsed=lambda t:self.clock,
            UnitAlive=lambda u:u not in self.dead, GetOwningPlayer=lambda u:self.owner[u],
            IsUnitType=lambda u,t:True, UNIT_TYPE_TOWNHALL='hall', UNIT_TYPE_STRUCTURE='structure',
            GetUnitX=lambda u:self.pos[u][0], GetUnitY=lambda u:self.pos[u][1],
            GetLocationX=lambda l:l[0], GetLocationY=lambda l:l[1], Location=lambda x,y:[x,y],
            MoveLocation=lambda l,x,y:l.__setitem__(slice(None),[x,y]),
            CreateGroup=list, GroupEnumUnitsOfPlayer=lambda g,p,f:g.extend(self.units),
            FirstOfGroup=lambda g:g[0] if g else None, GroupRemoveUnit=lambda g,u:g.remove(u),
            DestroyGroup=self.destroyed.append, GetLocationNonCreepStrength=strength)
        for name in ['IsRecoveryAnchorValid','UpdateRecoveryHome','GetRecoveryHome']:
            load_jass_function(self.env, 'RecoveryHome.eai', name)

    def update(self):
        self.env['UpdateRecoveryHome']()
        self.clock += 3

    def test_expo_defense_does_not_move_quiet_recovery_base(self):
        self.update()
        original = self.env['GetRecoveryHome']()
        self.env['captain_home'] = [-9000,5000]
        self.units.reverse()
        self.update()
        self.assertEqual(original, [0,0])
        self.assertIs(original, self.env['GetRecoveryHome']())
        self.assertEqual(self.env['recovery_anchor'], 'main')
        self.assertEqual(self.env['air_strength'], 42)

    def test_initial_selection_avoids_threatened_expo(self):
        self.danger['expo'] = 50
        self.units.reverse()
        self.update()
        self.assertEqual(self.env['recovery_anchor'], 'main')

    def test_threatened_main_switches_only_to_lower_danger(self):
        self.update()
        self.danger.update(main=30, expo=30)
        self.update()
        self.assertEqual(self.env['recovery_anchor'], 'main')
        self.danger['expo'] = 5
        self.update()
        self.assertEqual(self.env['GetRecoveryHome'](), [7300,0])
        self.assertEqual(self.env['air_strength'], 42)
        self.danger.update(main=0, expo=0)
        self.update()
        self.assertEqual(self.env['recovery_anchor'], 'expo')

    def test_destroyed_or_captured_anchor_is_replaced_even_during_throttle(self):
        for captured in [False,True]:
            self.setUp()
            self.update()
            self.clock = 1
            if captured:
                self.owner['main'] = 'enemy'
            else:
                self.dead.add('main')
            self.update()
            self.assertEqual(self.env['recovery_anchor'], 'expo')

    def test_no_hall_keeps_last_position_and_reacquires_new_hall(self):
        self.update()
        self.dead.update(self.units)
        self.update()
        self.assertIsNone(self.env['recovery_anchor'])
        self.assertEqual(self.env['GetRecoveryHome'](), [0,0])
        self.dead.remove('expo')
        self.update()
        self.assertEqual(self.env['recovery_anchor'], 'expo')

    def test_getter_has_no_scans_or_gameplay_side_effects(self):
        self.assertEqual(self.env['GetRecoveryHome'](), [0,0])
        self.assertIsNone(self.env['recovery_home'])
        self.assertEqual(self.env['air_strength'],42)
        self.assertEqual(self.destroyed,[])

    def test_pending_unit_is_not_recalled_by_defense_destination_change(self):
        self.update()
        recycled, jobs = [], []
        pending = {'hero'}
        self.env.update(IsUnitInGroup=lambda u,g:u in g, retreat_reset_pending=pending,
            IsRetreatTeleporting=lambda u:False, GetUnitLoc=lambda u:[0,0],
            DistanceBetweenPoints_dk=lambda a,b:abs(a[0]-b[0]), isfleeing=False,
            GroupRemoveUnit=lambda g,u:g.discard(u), ResetGuardPositionJob=recycled.append,
            TQAddUnitJob=lambda *a:jobs.append(a), in_retreat_group=set(),
            GroupAddUnit=lambda g,u:g.add(u), SEND_HOME=1)
        load_jass_function(self.env,'Jobs/RESET_RETREAT.eai','ResetRetreatJob')
        self.env['captain_home'] = [7300,0]
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(recycled,['hero'])
        self.assertEqual(jobs,[])
        self.assertEqual(pending,set())

    def test_tp_uses_recovery_anchor_and_skips_missing_anchor(self):
        self.update()
        orders, jobs = [], []
        self.env.update(teleporting=False, hero_unit={1:'hero'}, tp_item=1,
            teleportloc=None, TELEPORT=1, GoHomeIfMainHero=lambda *a:None,
            GetItemOfTypeOnUnit=lambda *a:'tp', GetRandomInt=lambda *a:300, ISign=lambda:1,
            UnitUseItemPoint=lambda *a:orders.append(a),
            TQAddUnitJob=lambda *a:jobs.append(a))
        load_jass_function(self.env,'Jobs/MICRO_HERO.eai','TeleportHome')
        self.env['TeleportHome'](1)
        self.assertEqual(orders,[('hero','tp',300,300)])
        self.assertEqual(self.env['teleportloc'],[0,0])
        self.env['teleporting'] = False
        self.dead.update(self.units)
        self.env['TeleportHome'](1)
        self.assertEqual(len(orders),1)
        self.assertFalse(self.env['teleporting'])
        self.assertEqual(len(jobs),1)

    def test_send_home_moves_to_recovery_then_holds_and_schedules_reset(self):
        self.update()
        moves, jobs, holds = [], [], []
        position = [1000,0]
        self.env.update(GetUnitState=lambda *a:100, UNIT_STATE_LIFE=1, UNIT_TYPE_HERO='hero',
            IsUnitType=lambda u,t:u in self.units, IsRetreatTeleporting=lambda u:False,
            IsUnitInGroup=lambda u,g:u in g, debug_retreat_transit_group=set(),
            in_retreat_group={'soldier'}, retreat_reset_pending=set(),
            DistanceBetweenPoints_dk=lambda a,b:abs(a[0]-b[0]), GetUnitLoc=lambda u:position,
            RemoveGuardPosition=lambda u:None, SendHomeMoveUnitToLoc=lambda u,l:moves.append((u,list(l))),
            TQAddUnitJob=lambda *a:jobs.append(a), SEND_HOME=1, RESET_RETREAT=2,
            IssueImmediateOrder=lambda *a:holds.append(a), RetreatRecovery=lambda u:False,
            GroupAddUnit=lambda g,u:g.add(u), GroupRemoveUnit=lambda g,u:g.discard(u))
        load_jass_function(self.env,'Jobs/SEND_HOME.eai','SendUnitHomeJob')
        self.env['SendUnitHomeJob']('soldier',1)
        self.assertEqual(moves,[('soldier',[0,0])])
        self.assertEqual(jobs,[(4,1,1,'soldier')])
        position[:] = [0,0]
        self.env['SendUnitHomeJob']('soldier',1)
        self.assertEqual(holds,[('soldier','holdposition')])
        self.assertEqual(self.env['retreat_reset_pending'],{'soldier'})
        self.assertEqual(self.env['in_retreat_group'],set())
        self.assertEqual(jobs[-1],(15,2,0,'soldier'))

    def test_recovery_paths_do_not_read_captain_destination(self):
        for path in ['Jobs/SEND_HOME.eai','Jobs/RESET_RETREAT.eai']:
            self.assertNotIn('captain_home',(ROOT/path).read_text())
        self.assertNotIn('captain_home',function_source('Jobs/MICRO_HERO.eai','TeleportHome'))
        rc=function_source('Jobs/RETREAT_CONTROL.eai','RetreatControlJob')
        self.assertIn('DistanceBetweenPoints(GetUnitLoc(u), GetRecoveryHome()) >= 650',rc)

    def test_capture_includes_tp_arrivals_without_counting_them_as_travellers(self):
        # Execute the actual capture-loop body; unrelated retreat-strength logic
        # needs the game engine and is deliberately not substituted here.
        source=function_source('Jobs/RETREAT_CONTROL.eai','RetreatControlJob')
        body=source.split('    set num_units = 0',1)[1].split('    call DestroyGroup(g)',1)[0]
        import test_retreat_ownership as parser
        original=parser.function_source
        jobs, removed = [], []
        g=['arrived','travelling','pending']
        positions={'arrived':0,'travelling':1000,'pending':0}
        env=dict(g=g,num_units=0,in_retreat_group=set(),retreat_reset_pending={'pending'},
            IsUnitInGroup=lambda u,g:u in g, IsStandardUnit=lambda u:u!='pending',
            IsUnitType=lambda *a:False, UNIT_TYPE_PEON=1, UNIT_TYPE_STRUCTURE=2,
            DistanceBetweenPoints=lambda a,b:abs(a-b), GetUnitLoc=lambda u:positions[u],
            GetRecoveryHome=lambda:0, GetUnitCurrentOrder=lambda u:0, OrderId=lambda s:99,
            FirstOfGroup=lambda g:g[0] if g else None, GroupRemoveUnit=lambda g,u:g.remove(u),
            GroupAddUnit=lambda g,u:g.add(u), SEND_HOME=1,
            RemoveGuardPosition=removed.append, TQAddUnitJob=lambda *a:jobs.append(a))
        try:
            parser.function_source=lambda p,n: ('function CaptureTest takes nothing returns nothing\n  local unit u = null\n'+body+'endfunction') if n=='CaptureTest' else original(p,n)
            load_jass_function(env,'Jobs/RETREAT_CONTROL.eai','CaptureTest')
        finally:
            parser.function_source=original
        env['CaptureTest']()
        self.assertEqual(removed,['arrived','travelling'])
        self.assertEqual(env['in_retreat_group'],{'arrived','travelling'})
        self.assertEqual(env['num_units'],1)
        self.assertEqual(len(jobs),2)

    def test_new_function_variables_do_not_shadow_globals(self):
        common=(ROOT/'common.eai').read_text().split('globals',1)[1].split('endglobals',1)[0]
        names=set(re.findall(r'^\s*(?:constant\s+)?\w+\s+(?:array\s+)?(\w+)',common,re.M))
        for name,args,body in re.findall(r'function (\w+) takes (.*?) returns \w+\n(.*?)endfunction',(ROOT/'RecoveryHome.eai').read_text(),re.S):
            declared=set(re.findall(r'local \w+ (\w+)',body))
            declared.update(a.split()[-1] for a in args.split(', ') if a!='nothing')
            self.assertFalse(declared & names,(name,declared & names))

if __name__ == '__main__':
    unittest.main()
