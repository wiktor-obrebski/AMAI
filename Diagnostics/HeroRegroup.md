# Returning heroes

Actual shopping completion/cancellation, normal reset, retreat reset (through
normal reset), and health-completion cleanup hand tracked heroes to `hero_regroup`.
A shopping request rejected or already satisfied before its first ownership
change leaves the hero untouched. The existing shopping start time identifies
that transition; a replacement shopper starts with fresh timers.
Healing thresholds and shopping policy are unchanged. Newly trained heroes and
ordinary reinforcements are outside this change's scope.

Regroup is an order lock, included in the existing retreat ownership predicate
so ordinary micro and stale resets cannot command the hero. The existing
MICRO_HERO loop maintains it; no new job or timeout is introduced. Emergency
retreat healing and TP remain available. Assault formation additionally skips
regroup-owned hero types because native AddAssault takes a type, not a handle.

Release has three explicit cases:

- New formation: at recovery, outside attack/flee/teleport states, and with no
  visible player enemy within 900, staged heroes count for planning and can be
  selected as the major hero. Remote town-threat flags do not disqualify them. They
  are released together immediately before InitAssault. This avoids starving
  early creeping or an army rebuilding around its returning hero.
- Active operation: calculate a rendezvous from the current positions of ready
  non-hero, non-summoned, non-illusion troops in the tracked main army. Its cached
  location is not used. At least two ready troops must be nearby and no visible
  player enemy may be there. Move toward this friendly rendezvous and retain control until
  within 500 with ready support nearby; proximity to the center alone does not
  stop the approach. Recheck the group every tick. Visible
  player enemies along the trip, or an unavailable group, redirect to recovery.
- Local defense: at least two ready troops and local friendly strength at least
  equal to visible enemy strength. A remote town-threat flag alone does not
  release the hero. Global fleeing suppresses this handoff.

Ownership is released through `ReleaseRegroupHero`, never by an unrelated reset.
`DBG HERO REGROUP BEGIN` and `DBG HERO REGROUP RELEASE` identify transitions;
existing hero order traces distinguish hold/move commands from native control.

## Validation and limits

Source-backed tests cover handoff, stale resets, planning/formation release,
native type exclusion, rendezvous arrival/loss, unavailable troops, visible
danger, defense, fleeing, death and teleport channels. These mocks do not prove
native captain behavior or Warcraft pathfinding.

This is deliberately conservative: a returning hero waits instead of joining an
already active battle across the map. There is no route planner; the current
position and destination checks cannot prove a safe route through a choke.
The two-troop and distance thresholds need game testing. Once a hero rejoins,
normal control can separate it again. This does not batch ordinary troops or
implement PR #8's reactive withdrawal check, nor PR #7's healing change.

For a gameplay test, check a full-health shopper returning after retreat, an
army moving away or dying during rendezvous, early creeping with one hero and
one troop, and both local and distant town threats. In particular, verify that
native formation does not acquire a hero before its REGROUP RELEASE trace.

Campaigns(7) follow-up tests cover shopping cancelled before/after detachment,
already satisfied requests, replacement shoppers, remote versus local threats,
major-hero selection, a moving army with an outdated cached position, and
rendezvous group/location ownership. These reproduce the source mechanisms;
they do not replay the recorded game.

Live positions eliminate the stale-center reversal mechanism, but an army
actually scattering, becoming unavailable, or encountering enemies can still
cause a return home. This does not make the army wait for a hero who misses its
formation, and does not change shopping frequency or native defense behavior.
