"""Run the actual small JASS ownership/reset functions with mocked Warcraft natives.

This checks scheduling and group ownership, not native captain behaviour or pathing.
Run: python -m unittest discover -s tests
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function_source(path, name):
    source = (ROOT / path).read_text()
    return re.search(rf'function {name} takes .*?\nendfunction', source, re.S).group()


def load_jass_function(env, path, name):
    """Translate only the straight-line/conditional JASS subset used here.

    Unsupported statements fail instead of silently substituting test behaviour.
    Debug output is ignored; every state check and native call is executed.
    """
    source = function_source(path, name).splitlines()
    args = source[0].split(' takes ')[1].split(' returns ')[0]
    args = '' if args == 'nothing' else ', '.join(a.split()[-1] for a in args.split(','))
    lines = [f'def {name}({args}):']
    locals_ = set(re.findall(r'^\s*local \w+ (\w+)', '\n'.join(source), re.M))
    assigned = set(re.findall(r'^\s*set (\w+)\s*=', '\n'.join(source), re.M))
    globals_ = assigned - locals_ - set(args.split(', '))
    if globals_:
        lines.append('    global ' + ', '.join(sorted(globals_)))
    indent = 1
    for raw in source[1:-1]:
        line = raw.split('//')[0].strip()
        if not line:
            continue
        if re.match(r'call (TraceAll|DisplayToAllJobDebug|CreateDebugTag)\(', line):
            lines.append('    ' * indent + 'pass')
            continue
        line = re.sub(r'\btrue\b', 'True', line)
        line = re.sub(r'\bfalse\b', 'False', line)
        line = re.sub(r'\bnull\b', 'None', line)
        if line in ('endif', 'endloop'):
            indent -= 1
            continue
        if line.startswith('local '):
            line = re.sub(r'^local \w+ ', '', line)
        elif line.startswith('set '):
            line = line[4:]
        elif line == 'loop':
            line = 'while True:'
        elif line.startswith('exitwhen '):
            line = 'if ' + line[9:] + ': break'
        elif line.startswith('elseif '):
            indent -= 1
            line = 'elif ' + line[7:-5] + ':'
        elif line == 'else':
            indent -= 1
            line += ':'
        elif line.startswith('if ') and line.endswith(' then'):
            line = line[:-5] + ':'
        elif line.startswith('call '):
            line = line[5:]
        elif not line.startswith('return'):
            raise AssertionError(f'Unsupported JASS statement: {line}')
        lines.append('    ' * indent + line)
        if line.endswith(':'):
            indent += 1
            lines.append('    ' * indent + 'pass')
    exec('\n'.join(lines), env)
    # Execute actual diagnostic passthrough wrappers in existing behaviour tests.
    # Their logging is disabled here; dedicated tests also exercise enabled logging.
    if path != 'Diagnostics/HeroOrders.eai':
        env.setdefault('debug_hero_tracking', False)
        for wrapper in set(re.findall(r'\b(DebugHero\w+)\(', '\n'.join(source))):
            if wrapper not in env:
                load_jass_function(env, 'Diagnostics/HeroOrders.eai', wrapper)
        if 'DebugHeroOrderAfter' not in env:
            load_jass_function(env, 'Diagnostics/HeroOrders.eai', 'DebugHeroOrderAfter')


class RetreatOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.recycled = []
        self.assault = []
        self.jobs = []
        self.dead = set()
        self.env = dict(
            isfleeing=False, attack_running=True,
            IsRetreatTeleporting=lambda u: False, RetreatRecovery=lambda u: False,
            captain_home=0, GetUnitLoc=lambda u: 0,
            DistanceBetweenPoints_dk=lambda a, b: abs(a-b),
            GroupAddUnit=lambda g, u: g.add(u), SEND_HOME='send_home',
            UNIT_TYPE_PEON='peon', UNIT_TYPE_STRUCTURE='structure',
            UNIT_STATE_LIFE='life', UNIT_STATE_MAX_LIFE='max_life',
            PLAYER_NEUTRAL_AGGRESSIVE=12, RESET_HEALTH='health', RESET_RETREAT='retreat',
            IsUnitInGroup=lambda u, g: u in g,
            GroupRemoveUnit=lambda g, u: g.discard(u),
            RecycleGuardPosition=self.recycled.append,
            UnitAlive=lambda u: u not in self.dead,
            IsUnitVisible=lambda u, p: True, Player=lambda p: p,
            IsUnitType=lambda u, t: False, GetUnitTypeId=lambda u: 'Udea',
            GetUnitState=lambda u, s: 100, I2R=float,
            AddAssault=lambda *a: self.assault.append(a),
            TQAddUnitJob=lambda *a: self.jobs.append(a),
        )
        for g in ('in_retreat_group', 'retreat_reset_pending', 'unit_healing',
                  'unit_rescueing', 'unit_harassing', 'unit_zepplin_move'):
            self.env[g] = set()
        for name in ('IsRetreatOrderLocked', 'RecycleGuardPositionAM', 'IsStandardUnit',
                     'IsRetreatUnavailableForAttack'):
            load_jass_function(self.env, 'common.eai', name)
        for job, name in (
            ('RESET_GUARD_POSITION', 'ResetGuardPositionJob'),
            ('RESET_GUARD_POSITION_ONLY', 'ResetGuardPositionOnlyJob'),
            ('RESET_WINDWALKER', 'ResetWindWalkerGuardPosition'),
            ('RESET_HEALTH', 'ResetByHealthJob'),
            ('RESET_RETREAT', 'ResetRetreatJob'),
        ):
            load_jass_function(self.env, f'Jobs/{job}.eai', name)

    def test_all_non_retreat_resets_leave_both_owned_states_untouched(self):
        for group in ('in_retreat_group', 'retreat_reset_pending'):
            for fleeing in (False, True):
                with self.subTest(group=group, fleeing=fleeing):
                    self.env[group].add('hero')
                    self.env['isfleeing'] = fleeing
                    self.env['unit_healing'].add('hero')
                    self.env['RecycleGuardPositionAM']('hero')
                    self.env['ResetGuardPositionJob']('hero')
                    self.env['ResetGuardPositionOnlyJob']('hero')
                    self.env['ResetWindWalkerGuardPosition']('hero')
                    self.env['ResetByHealthJob']('hero', 80)
                    self.assertIn('hero', self.env[group])
                    self.assertIn('hero', self.env['unit_healing'])
                    self.assertEqual(self.recycled, [])
                    self.assertEqual(self.assault, [])
                    self.assertEqual(self.jobs, [])
                    self.assertFalse(self.env['IsStandardUnit']('hero'))
                    self.assertTrue(self.env['IsRetreatUnavailableForAttack']('hero'))
                    self.env[group].clear()

    def test_owner_defers_then_releases_and_normal_control_resumes(self):
        self.env['retreat_reset_pending'].add('hero')
        self.env['isfleeing'] = True
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(self.jobs, [(5, 'retreat', 0, 'hero')])
        self.assertEqual(self.recycled, [])
        self.env['isfleeing'] = False
        # An unrelated old reset is still not allowed to finish recovery early.
        self.env['ResetGuardPositionJob']('hero')
        self.assertEqual(self.recycled, [])
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(self.recycled, ['hero'])
        self.assertTrue(self.env['IsStandardUnit']('hero'))
        self.env['ResetRetreatJob']('hero')
        self.assertEqual(self.recycled, ['hero'])
        self.env['ResetGuardPositionOnlyJob']('hero')
        self.assertEqual(self.assault, [(60, 'Udea')])

    def test_dead_pending_unit_is_cleaned_without_waiting_for_global_retreat(self):
        self.env['retreat_reset_pending'].add('hero')
        self.env['unit_healing'].add('hero')
        self.env['isfleeing'] = True
        self.dead.add('hero')
        self.env['ResetRetreatJob']('hero')
        self.assertFalse(self.env['IsRetreatOrderLocked']('hero'))
        self.assertNotIn('hero', self.env['unit_healing'])
        self.assertEqual(self.jobs, [])

    def test_travellers_still_pass_retreat_tracking_but_pending_units_do_not(self):
        source = (ROOT / 'Jobs/RETREAT_CONTROL.eai').read_text()
        condition = re.search(r'if (\(IsUnitInGroup\(u, in_retreat_group\).*?) then', source).group(1)
        self.env.update(u='hero', captain_home=0, GetUnitLoc=lambda u: 1000,
                        DistanceBetweenPoints=lambda a, b: abs(a - b))
        self.env['in_retreat_group'].add('hero')
        self.assertTrue(eval(condition, self.env))
        self.env['in_retreat_group'].clear()
        self.env['retreat_reset_pending'].add('hero')
        self.assertFalse(eval(condition, self.env))

    def test_stale_healing_group_does_not_move_owned_members(self):
        orders = []
        self.env.update(CopyGroup=lambda g: set(g),
                        FirstOfGroup=lambda g: next(iter(g), None),
                        DestroyGroup=lambda g: g.clear(),
                        IssuePointOrder=lambda *args: orders.append(args))
        load_jass_function(self.env, 'common.eai', 'GroupPointOrderAvailable')
        group = {'traveller', 'pending', 'ready'}
        self.env['in_retreat_group'].add('traveller')
        self.env['retreat_reset_pending'].add('pending')
        self.env['GroupPointOrderAvailable'](group, 'move', 10, 20)
        self.assertEqual(orders, [('ready', 'move', 10, 20)])
        self.assertEqual(group, {'traveller', 'pending', 'ready'})

    def test_raw_ai_recycling_cannot_bypass_the_shared_gate(self):
        # Blizzard map scripts run in another VM; this audits the AMAI sources.
        for path in [ROOT / 'common.eai', *(ROOT / 'Jobs').glob('*.eai')]:
            active = '\n'.join(line.split('//')[0] for line in path.read_text().splitlines())
            count = len(re.findall(r'\bcall (?:DebugHero)?RecycleGuardPosition\(', active))
            self.assertEqual(count, 1 if path.name == 'common.eai' else 0, path)
        wrapper = function_source('common.eai', 'RecycleGuardPositionAM')
        self.assertIn('call DebugHeroRecycleGuardPosition(u,', wrapper)
        native_wrapper = function_source('Diagnostics/HeroOrders.eai', 'DebugHeroRecycleGuardPosition')
        self.assertEqual(native_wrapper.count('call RecycleGuardPosition(u)'), 1)


if __name__ == '__main__':
    unittest.main()
