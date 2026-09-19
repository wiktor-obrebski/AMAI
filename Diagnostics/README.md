# Hero attack diagnostics

This diagnostic build records heroes throughout the game, including heroes that
never entered either retreat group. It does not implement a retreat/defense fix.

## Build and collect

Run the full `MakeREFORGED.bat` and install the rebuilt AI scripts **and the
rebuilt `Blizzard.j`** into the test map using the normal AMAI installation flow.
Replacing only `common.ai` does not install the map event observer. Generated
`Scripts/` files are not committed in this PR.

Start a fresh game; collect `Campaigns.w3v` after the incident, as before. It holds
the following logical caches. Each uses `P<zero-based player id>`, `Count`, and
`L0` through `L(Count-1)`:

| Logical cache | Records |
| --- | --- |
| `AMAI_Trace.w3v` | Existing attack/retreat diagnostics, unchanged |
| `AMAI_HeroTrace_P<id>.w3v` | AI order sources/results, control writes, hero snapshots/support |
| `AMAI_HeroEvents.w3v` | Map-side issued-order events, including orders without an AI source marker |

Check for `HERO TRACKING START: version=3` and `HERO EVENT OBSERVER START: version=1`.
If the latter is missing, do not interpret absent order events as absent orders.
The map observer registers immediate, point and target order events for computer
players. It does not claim that every native AI action emits such an event.

AI records use `tq_timer`, matching the old trace. Map records use a separate
elapsed timer started in `InitBlizzard`. **Do not directly compare their `tms`
values without aligning the clocks.** Match several unambiguous explicit orders
by hero handle, order kind/ID and target/coordinates; estimate the timestamp
offset from those matches. Repeated identical orders can make attribution
ambiguous. Do not force a match. No synchronization or shared gameplay state is
introduced to correlate the VMs.

## Read the evidence

- `HERO ORDER SOURCE` identifies the file, leaf function and original source-line
  label that calls a native. Labels are stable identifiers from the pre-patch
  source, not current editor line numbers. `request` joins the source and result
  within one player's AI stream. Arguments are evaluated once before the wrapper;
  its diagnostic reads do not repeat expressions such as random coordinates.
- `HERO ORDER RESULT accepted=false` means the native rejected the attempt.
  Acceptance is not proof that movement, an item effect, or combat completed.
- For ordinary orders, `order` is the order ID. For `item*` source records it is
  the **item type ID**, not the engine's issued-order ID. Match item events by
  hero, time and target, not by equating these two numbers.
- `HERO ORDER EVENT` records what the map event system reports, with hero identity,
  position, HP and point/widget target. It does not know the issuing subsystem.
  **An event with no matching source is unknown, not proven native AI.** Map
  triggers, native behavior, shared control, or missing coverage are possibilities.
- `HERO CONTROL` marks captain-home/attack/formation calls and hero guard removal
  or restoration. These can explain a change in native ownership without a
  directly issued hero order. A nearby control marker is context, not proof of
  causation. Leaf markers do not provide a full call stack or explain why a job
  was scheduled.
- `HERO SNAPSHOT` and its following `HERO SUPPORT` share a hero handle and timestamp.
  They run about every two seconds without sleeps inside a sample. They cover
  all enumerated own heroes, including illusions and dead handles while those
  remain enumerable. `alive`, `illusion` and `loaded` disambiguate them.
- Support radius is 900; the sampled hero is excluded. `ownCount` counts physically
  nearby own living, non-hidden, unloaded, non-peon, non-building units. `readyCount`
  further requires `IsStandardUnit` and not `IsUnitBuying`. These are diagnostic
  eligibility checks, not guarantees of pathing, attack capability, or intent;
  for example a non-peon harvesting Ghoul can still be nearby. `own`, `ready`,
  `ally` and `visibleEnemy` use existing per-unit strength weights (including HP
  and hero/healing rules), not the aggregate helpers that mutate `air_strength`.
  Enemy values include only visible, non-invisible enemies and can include creeps.
  `mainDistance` uses the cached main-army position; it is not measured cohesion.

For a solo attack, find where support disappears or the hero moves away, inspect
orders/events immediately before that interval, then inspect the corresponding
source and control markers and retreat membership. A hero carrying an attack
order alone does not prove it attacked an enemy. HP changes, target, positions,
support and the replay are complementary evidence.

## Safety and limits

AI-side formatting uses AMAI `Int2Str`: native `I2S` is not supported in the AI
VM even though JASS compilation accepts it. The map observer uses map-VM `I2S`.
The formation regression test executes the logger instead of mocking it away;
it checks cache names, record keys and that the formation native is reached.
This does not reproduce Warcraft VM failures or prove the opening stall is fixed.

- Native order wrappers call the original native once with unchanged arguments
  and preserve its return value. All traces are single-line JASS statements.
- No tactical thresholds, ownership rules, unit orders or random calls are added
  by the observers. No aggregate strength queries are used.
- Temporary groups are destroyed. Diagnostic cache writes are buffered and saved
  every five seconds on the map side and approximately six seconds on the AI
  side. An abrupt exit can lose the last unsaved tail. Existing TraceAll flushing
  is unchanged. Separate logical caches avoid a map observer overwriting an AI
  cache object. Each AI also uses a distinct hero-trace cache name to avoid two
  AI VMs saving different snapshots of the same cache. Multi-AI save behavior
  is not gameplay-tested.
- Logging allocates strings, scans nearby units and writes growing cache files.
  It is not zero-cost; game performance and engine event delivery still require
  an actual Warcraft test. At three heroes the snapshots alone produce roughly
  5,400 records in 30 minutes, plus order/control records.
- Disable `debug_hero_tracking` in `HeroTraceGlobals.eai` and
  `amai_hero_event_tracking` in `HeroMapGlobals.eai` and rebuild to turn off these
  diagnostics. Wrappers then pass through with a small function-call overhead.

Validation: `python -m unittest discover -s tests`; generated Reforged common and
four race scripts and both map variants checked with pjass. Source-level tests
cover enabled/disabled order wrappers, rejection results, map event fields,
physical support and unchanged gameplay globals. They do not emulate native
captain behavior, event delivery, pathing or actual combat.

## Retreat investigation (version 2)

This build adds no target clearing or retreat behavior. Keep the existing map
observer installed; its format remains version 1.

- `ATTACK LIFECYCLE` records operation begin/end, attack-loop exit/early return,
  command issue and explicit `ClearCaptainTargets` calls. It includes attack,
  break, canFlee, fleeing and retreat-control flags.
- `ATTACK COMMAND` identifies the scripted target handle/coordinates and a unique
  command number. Repeated submissions to the same target remain separate events.
- Major AMAI attack entry points receive operation IDs. Nested operations restore
  their parent ID on return. Operation 0 means outside those instrumented scopes;
  it does not mean Warcraft has no native target. Ending an operation does not
  imply that `ClearCaptainTargets` was called.
- Hero source/control/snapshot records now include the current operation and
  latest command number. The latest command is correlation context, not proof
  of the hero's assignment or of the native captain's internal target.
- `HERO RETREAT MEMBERSHIP` records each scripted add/remove to the existing
  retreat groups, after that mutation. Sequential arrival transitions may show
  both groups briefly; read the following transition too. `STATE_WRITE` records
  changes in the retreat and hero-teleport paths.

Align the existing map clock with the AI clock before correlating orders. Use
membership transitions and state writes around an order to distinguish a locked
hero, a hero never captured, and a hero released after retreat ended. Two-second
snapshots alone are not event-time state. An unmatched map event has an unknown
writer, not a proven native writer; events and clock matching can be incomplete.

Command wrappers cover calls in AMAI `common.eai`; legacy helpers in
`common_original.eai` and Warcraft internals are not instrumented by this change.
No new cross-VM state transfer or event callback is introduced.

Validation includes argument passthrough with tracing enabled/disabled, nested
operation IDs, and comparison of changed gameplay statements against baseline
404a07a after removing diagnostic statements and unwrapping calls. Diagnostic
I/O adds overhead even though gameplay statements are unchanged. Warcraft runtime
behavior and cross-clock correlation still require a fresh game log.

## Immediate control-call effects (version 3)

`HERO CONTROL` now has paired `phase=BEFORE` / `phase=AFTER` records, joined by
`call` within one player's AI log. BEFORE includes source, action, arguments,
operation/attack-command context, retreat flags and captain state. AFTER includes
captain state and, for `AddAssault`, its unchanged boolean result. Calls receive
IDs even when they do not change any hero order. A missing AFTER is incomplete
execution or capture, not evidence of a successful call.

Between each pair, `HERO CONTROL STATE` records every non-null `hero_unit[1..3]`
slot immediately before and after the original call, using the existing hero
state fields (handle, position, HP, current order, retreat/pending and job flags).
Guard calls also sample their hero argument if absent from those slots. No
additional unit enumeration or nearby-strength scan runs per call. Extra/custom
heroes outside that roster remain covered by periodic snapshots and map events,
but are not included in captain-call samples. Guard calls on nonheroes pass
through without these records.

Covered wrappers: `RemoveGuardPosition`, `RecycleGuardPosition`, `InitAssault`,
`AddAssault`, `SetCaptainHome`, `CaptainGoHome`, `CaptainAttack`, `AttackMoveKill`,
`AttackMoveXY` and `ClearCaptainTargets`. Coverage is at the existing AMAI wrapper
sites; calls inside `common_original.eai` and the engine are still outside it.
Sources remain leaf-function labels, not call stacks: for example, a release
through `RecycleGuardPositionAM` identifies that shared helper. An `AddAssault`
request is by type/count; the log does not assert which handles it recruited.

To investigate shopping release or conflicting home/outward orders:

1. Find the map order event and align its clock as described above.
2. Compare that hero's BEFORE/AFTER `current` values for the nearby guard and
   captain calls. A change brackets an immediate effect of that call; it is
   strong evidence, not an internal engine stack trace.
3. If both orders are unchanged, an identical-order reissue or a change and
   reversal within the call remains possible. Consult map events. Equal order
   IDs do not prove equal destinations: AI samples cannot query the current
   order's target, and a move can be retargeted while keeping its order ID.
4. If the event occurs later, retain unknown attribution. Read preceding
   `RecycleGuardPosition`, `AddAssault`, home changes and target commands/clears
   in call-ID order. Hero state records include `controlCall`, the latest issued
   wrapped control call, as correlation context only. It is not the last writer
   of that hero's order, nor an active engine target.

The map observer is unchanged (version 1); the AI start marker is now version 3.
Keep the observer installed. AI call pairs can be compared without clock alignment,
but locating a map event inside a pair still requires sufficiently precise clock
alignment; an uncertain boundary must remain uncertain. No shared mutable
"current caller" or cross-VM callback is introduced.

This remains tracking-only: no added target clearing, orders, ownership changes,
waits or tactical conditions. With three roster heroes, a control call adds six
state records and two call records; frequent formation calls can substantially
grow the log and add timing overhead. The existing flags disable this tracing.
Tests exercise native argument/result passthrough, immediate and delayed mocked
effects, call IDs, roster/focus handling and byte-identical gameplay sources.
They do not establish native engine causality or Warcraft runtime safety.
