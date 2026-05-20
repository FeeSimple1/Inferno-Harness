# Strategy Digest — Inferno

Advisory tactical and strategic priors for the LLM consumer. This file
is NOT loaded or parsed by the harness; the LLM is free to apply,
adapt, disagree with, or ignore any of it.

Strategy advice belongs HERE — never in `src/inferno/`. If a harness
helper output or comment contains language like "use when…", "prefer…",
"should…", or any other action prescription, that's a bug. See
[`BRIEF.md`](BRIEF.md) → "No Agent in the Harness".

Source material for the digest, as the project develops:
- Inferno Playbook "On Strategy" (pp. 4–6).
- Inferno Playbook "Solitaire" (p. 6).
- Inferno Playbook "Campaign History" (pp. 19–32) — read for
  game-mechanical context only; ignore historical claims (see BRIEF).
- This project's `SMOKE_TEST_FINDINGS.md` and `PLAYTESTS.md` as they
  accumulate.

---

## Observed priors (from self-play sweeps, v1.5–1.7)

These are advisory — derived from automated greedy + strategic agent
sweeps across all 6 scenarios × many seeds, plus the rules text. Apply,
adapt, or ignore.

Tempo & Levy
- Muster aggressively in Levy 3.4: each Mustered Lord that can Fealty-
  roll a waiting Lord onto the map adds a future Command card. Lordship
  is the binding constraint; spend it before `levy_muster_done`.
- Pay (3.2) to push Service markers right is cheap insurance against
  early Disband. Podestà cost 2 Coin/box, so prioritise non-Podestà
  shifts when Coin is tight.

Campaign
- Forage at a Friendly Stronghold is automatic and free of Transport —
  the safe default for keeping Lords fed. Outside friendly Strongholds
  it is seasonal (no Winter forage in the open).
- Ravage of enemy Towns/Cities yields Loot (good for Pay-with-Loot and
  Bribe Coin) but costs your side ½ VP per marker. Net VP can go
  negative — Ravage for the economy, not the score.
- Sieges, Storms, and any Battle end the current Command card. If you
  plan to Besiege, expect the card to end immediately — sequence other
  actions (Forage/Ravage/Supply) before the Besiege step, or Bypass to
  keep acting.

Combat
- Defending with Hills (F6/S6) doubles your Archery — but Lord-mat
  Archery only fires with Arcieri/Luceria/Balestrieri in play, so Hills
  pairs with those.
- Feditori (Cavalieri ×2 in R1–R2) front-loads Battle damage; Army
  Reserve (×2 from R3) rewards a grind. Pick the Capability that matches
  your expected Battle length.
- Concede halves your Hits this Round but caps your losses and Service
  shift — Concede when you've already lost the exchange.

Scenario notes
- Scenario E doubles Guelph VP (except Ravaged) — Guelph should grab
  Allegiance markers; Ghibelline should Ravage to deny doubled value.
- Scenario C: Ghibellines can't cross the dashed line until the Guelphs
  commit aggression (Siege/Ravage). Bait the Guelph into the south.
- Scenario F (full-length): Exhaustion rolls from Turn 9 can end the
  game early — bank VP before the End marker creeps in.

## Source material for ongoing expansion
- Inferno Playbook "On Strategy" (pp. 4–6).
- Inferno Playbook "Solitaire" (p. 6).
- `SMOKE_TEST_FINDINGS.md` + `PLAYTESTS.md` as they accumulate.
