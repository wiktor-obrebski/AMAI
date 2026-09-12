# Recovery destination versus captain home

Retreat formerly reused `captain_home`, which army tracking can move to a threatened
expansion while native captain home may even point at the enemy army. The game-4
trace shows a recovery destination change of about 7,300 units, with 21 units put
back into retreat travel after arrival. This is evidence of destination coupling;
it does not prove that the location change caused every subsequent loss.

Recovery now uses a separate, owned location anchored to a living owned town hall.
Initial selection minimizes nearby enemy combat strength, then distance from the
starting location. A quiet existing anchor is retained regardless of town value,
mine depletion, or defense orders. An exposed anchor changes only when another
owned hall has strictly less nearby enemy strength. A destroyed, captured, or
uprooted anchor triggers reselection. Selection uses live units rather than town
indices, so town-array compaction cannot change its identity.

The check uses the existing non-creep enemy-strength helper within 1,500 units.
It restores that helper's `air_strength` side effect. Refreshes are limited to
once per two seconds of demand, except loss of an existing anchor is checked
immediately. There are no sleeps, new random draws, or captain-home writes in
selection. `GetRecoveryHome()` only reads the cached location (or the starting
location before initialization); diagnostics cannot trigger a selection.

Forced retreat capture, movement, arrival/reset checks, SEND_HOME healing movement,
and emergency home TP use this destination. Retreat capture also owns units that
are already at recovery, including TP arrivals, so native guard control cannot
immediately take them back out. Only distant units count as still travelling.
Existing retreat locks, recovery timers, and reset release remain in effect.

When no owned town hall survives, walking recovery keeps the last location (the
start before any anchor was selected). Emergency home TP is skipped instead of
using an invalid owned hall or the tactical defense destination. Allied bases
are not considered by this selector. This fallback is not claimed to be safe.

## Diagnostics and validation

- `DBG RECOVERY HOME` records anchor changes, reason, location, nearby enemy
  estimate, and cached captain-home coordinates. Native captain-home writes still
  appear separately in `HERO CONTROL`; the cached and native destinations can differ.
- Hero records retain `homeX/homeY/distHome` for cached captain home and add
  `recoveryX/recoveryY/recoveryAnchor`. Anchor 0 means none has been selected or none
  survives. Recovery coordinates before initialization are 0 in these raw snapshots.
- Retreat transit `distHome` now measures the recovery destination.
- Source-backed tests exercise actual selection, capture, SEND_HOME, reset and TP
  functions with mocked Warcraft natives. All Reforged AI scripts compile with
  pjass; the explicit shadow check has only the nine pre-existing unrelated errors.

Rebuild and install the changed AI scripts, then start a fresh game. Check the
blocked-expansion case: when the main hall remains quiet, defense may change home
but recovery should stay at the main. Also check main-base invasion, destruction
of the recovery hall, TP arrival with a distant defense target, and recovery with
only one remaining besieged base. Those cases need Warcraft runtime validation.

## Deliberate limits

This change does not assess routes, chokepoints, unreachable terrain, enemy towers,
or neutral creeps. Lower enemy strength at the endpoint does not prove safe access.
The existing strength helper is not restricted to visible enemies. An all-bases-
threatened situation therefore has no guaranteed safe result.

This PR does not change native defense assignments after reset release, coordinate
a whole-army release, or make new heroes rendezvous before reinforcement. Those
remain separate work; a normal attack-strength gate cannot govern every native
defense order. Recovery/defense separation is the first change, not a claim that
all observed small-group attacks are fixed.
