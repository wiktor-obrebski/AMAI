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

Check for `HERO TRACKING START: version=1` and `HERO EVENT OBSERVER START: version=1`.
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
