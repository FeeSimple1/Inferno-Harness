"""Deterministic policy adapted from the recorded seed-20261012 playtest.

These priorities select TEST actions from the full menu. They do not limit
what any real player can retrieve. Never use this module in the LLM boundary.
"""
import collections
from inferno import actions as ac, static_data as sd, card_data as cd
from benchmarks import endurance_support as p

def plan_for(side):
    slots = sd.PLAN_SIZE_BY_SEASON[sd.SEASON_BY_BOX[s['meta']['turn']]]
    ordinary = [(lid, l) for lid, l in p.own_lords(side).items() if not l.get('comune_of')]

    def urgency(item):
        lid, l = item
        loc = l['location']
        cost = 2 if l.get('podesta') else 1
        u = 3 + int(l.get('commander', False))
        if s['locales'][loc].get('siege'):
            u += 4
        if (l.get('service_box') or 99) <= s['meta']['turn'] + 1 and l['assets'].get('Coin', 0) < cost * 2:
            u += 5
        if loc in l['seats'] and l['assets'].get('Coin', 0) < cost * 2:
            u += 2
        return u
    ordered = sorted(ordinary, key=lambda x: (-urgency(x), x[0]))
    chosen = []
    counts = collections.Counter()
    for lid, l in ordered[:slots]:
        chosen.append('command_' + lid)
        counts[lid] += 1
    while len(chosen) < slots:
        candidates = [x for x in ordered if counts[x[0]] < 3]
        if not candidates:
            chosen.append('PASS')
            continue
        lid, l = max(candidates, key=lambda x: urgency(x) - counts[x[0]] * 4)
        chosen.append('command_' + lid)
        counts[lid] += 1
    return chosen

def cta_choice(ms):
    names = {m['action'] for m in ms}
    side = s['meta']['active_player']
    skip = next((m for m in ms if m['action'] in ('cta_step_skip', 'levy_cta_skip')), None)
    if 'levy_cta_declare' in names:
        return (next((m for m in ms if m['action'] == 'levy_cta_declare')), 'Declare an eligible Call to Arms for reinforcement and refit.')
    if 'levy_muster_done' in names:
        return p.muster_choice(ms)
    if 'cta_gather_march' in names:
        candidates = []
        for m in ms:
            if m['action'] != 'cta_gather_march':
                continue
            lid = m['args']['lord_id']
            l = s['lords'][lid]
            if l.get('comune_of'):
                continue
            if (l.get('service_box') or 99) <= s['meta']['turn'] + 1 and l['assets'].get('Coin', 0) < 3:
                candidates.append(m)
        if candidates:
            return (min(candidates, key=lambda m: (p.distance(m['args']['destination'], ac.LEADING_CITY[side]), m['args']['lord_id'])), 'Gather an underfunded, expiring contingent toward its Leading City.')
    if 'cta_commander_arms' in names:
        cmd = s['lords'][ac.COMMANDER_LORD[side]]
        muster = next((m for m in ms if m.get('args', {}).get('mode') == 'muster_only'), None)
        recall = next((m for m in ms if m.get('args', {}).get('mode') == 'disband_and_remuster'), None)
        if muster:
            return (muster, 'Return the Commander from the Calendar at the normal Call to Arms opportunity.')
        if recall and ((cmd.get('service_box') or 99) <= s['meta']['turn'] + 1 or p.force_n(cmd) <= 2 or cmd['assets'].get('Provender', 0) == 0):
            return (recall, 'Recall and remuster an expiring or depleted Commander; his Comune must follow the legal lifecycle.')
    if 'cta_comune_setup' in names:
        opts = [m for m in ms if m['action'] == 'cta_comune_setup']

        def rank(m):
            prev = ac._comune_setup_preview(s, side, m.get('args', {}))
            count = sum(prev['forces'].values())
            return (-abs(count - 8), len(prev['added']))
        return (max(opts, key=rank), 'Muster fresh Special Vassals into a useful Comune without assuming casualties or assets refresh.')
    if 'cta_allies' in names:
        opts = [m for m in ms if m['action'] == 'cta_allies']
        live = sum((not l.get('comune_of') for l in p.own_lords(side).values()))
        auto = [m for m in opts if m['args']['mode'] == 'auto_muster']
        if auto and live < 5:
            return (auto[0], 'Use Allies to bring a ready Lord onto the map without a Fealty roll.')
        extra = [m for m in opts if m['args']['mode'] == 'extra_muster']
        if extra:
            return (max(extra, key=lambda m: (s['lords'][m['args']['target_lord_id']].get('commander', False), -p.force_n(s['lords'][m['args']['target_lord_id']]))), 'Spend an eligible Lord’s Allies Muster segment on support for the next campaign.')
        if auto:
            return (auto[0], 'Bring an available reinforcing Lord into play.')
    if skip:
        return (skip, 'Skip this optional step when no useful legal benefit remains.')
    return None

def choose(ms):
    names = {m['action'] for m in ms}
    meta = s['meta']
    side = meta['active_player']
    if any((x in names for x in ('cmd_resolve_revolt', 'cmd_resolve_exiles', 'cmd_fpd_pay_done', 'approach_response', 'besiege_or_bypass'))):
        return p.campaign_choice(ms)
    if meta['phase'] == 'levy':
        if 'levy_resolve_event' in names:
            return p.event_choice(ms)
        if 'levy_place_capability' in names:
            opts = [m for m in ms if m['action'] == 'levy_place_capability' and (not m.get('args', {}).get('discard'))]
            return ((opts or ms)[0], 'Place a drawn Capability on an eligible Lord.')
        if 'levy_aow_draw' in names:
            return (next((m for m in ms if m['action'] == 'levy_aow_draw')), 'Draw the next Arts of War cards normally.')
        if 'levy_pay_done' in names:
            return p.upkeep_choice(ms)
        if 'levy_disband' in names:
            return (next((m for m in ms if m['action'] == 'levy_disband')), 'Resolve Lords whose Service has actually expired.')
        if 'levy_disband_done' in names:
            return (next((m for m in ms if m['action'] == 'levy_disband_done')), 'Complete Disband.')
        if meta.get('levy_step') == '3.5':
            return cta_choice(ms)
        if 'levy_muster_done' in names:
            return p.muster_choice(ms)
    step = meta.get('campaign_step')
    if step == 'capability_discard':
        done = [m for m in ms if m['action'] == 'campaign_discard_done']
        if done:
            return (done[0], 'Retain legal Capabilities and complete the limit check.')
        opts = [m for m in ms if m['action'] == 'campaign_discard_capability']
        if opts:
            return (min(opts, key=lambda m: p.CAP_PRIORITIES.get(cd.AOW_CARDS_BY_ID[m['args']['card_id']]['capability_name'], 0)), 'Discard the least useful excess Capability.')
    if step == 'plan':
        pk = f"{meta['turn']}:{side}"
        if pk not in plans:
            plans[pk] = plan_for(side)
            pass  # Test policy plan recorded by benchmark actions, not printed.
        count = len(s['plan_stacks'][side])
        wanted = plans[pk][count] if count < len(plans[pk]) else None
        if wanted:
            match = next((m for m in ms if m['action'] == 'plan_add_card' and m['args']['card_id'] == wanted), None)
            if match:
                return (match, 'Allocate Command cards to live Lords, prioritizing finance and ongoing sieges.')
        done = next((m for m in ms if m['action'] == 'plan_done'), None)
        if done:
            return (done, 'Complete the full seasonal plan.')
        return None
    if step == 'command_phase':
        return p.campaign_choice(ms)
    if step == 'end_campaign':
        for name in ('end_grow', 'end_grow_skip', 'end_ransom', 'end_game_check', 'end_repair', 'end_waste', 'end_reset'):
            opts = [m for m in ms if m['action'] == name]
            if opts:
                if name == 'end_ransom':
                    opts.sort(key=lambda m: not m.get('args', {}).get('pay', True))
                return (opts[0], 'Resolve the ordinary end-of-campaign sequence; never suppress victory or Exhaustion.')
    return None

class EndurancePolicy:
    def __init__(self):
        self.plans = {}

    def choose(self, state, moves):
        global s, plans
        s = state
        plans = self.plans
        p.s = state
        picked = choose(moves)
        if not picked or not picked[0]:
            raise AssertionError('Endurance policy needs an explicit decision for this complete menu.')
        return picked[0]
