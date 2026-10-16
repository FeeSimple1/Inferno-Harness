"""Prior Scenario F test policy; advisory test decisions, never UI filtering."""
import math
from collections import deque
from inferno import actions as ac, static_data as sd, card_data as cd

orders = {'arezzo': ['Cortona', 'Montepulciano', 'Asinalunga', 'San Quirico'], 'firenze': ['Poggio Bonizio', 'Casole', 'San Gimignano', 'Volterra'], 'colle': ['Casole', 'San Gimignano', 'Volterra'], 'lucca': ['Pontedera', 'Castelfiorentino', 'Volterra'], 'guido_guerra': ['Vernio', 'Cantagallo', 'Montemurlo'], 'orvieto': ['Montepulciano', 'San Quirico', 'Radicofani'], 'siena': ['Montalcino', 'Montepulciano', 'Volterra', 'Colle'], 'provenzano': ['Montalcino', 'Montepulciano', 'Volterra', 'Colle'], 'santa_fiora': ['Grosseto', 'Montemassi', 'Montepescali', 'Montalcino'], 'giordano': ['Casole', 'Colle', 'Poggio Bonizio'], 'astimberg': ['Casole', 'Colle', 'Poggio Bonizio'], 'pisa': ['Pontedera', 'San Miniato', 'Lucca']}

def friendly(name, side):
    return ac._is_friendly_locale(s, s['locales'][name], side)

def distance(a, b):
    if a == b:
        return 0
    q = deque([(a, 0)])
    seen = {a}
    while q:
        n, d = q.popleft()
        for nn, _ in sd.adjacent_to(n):
            if nn == b:
                return d + 1
            if nn not in seen:
                seen.add(nn)
                q.append((nn, d + 1))
    return 999

def own_lords(side, at=None):
    return {k: l for k, l in s['lords'].items() if l['side'] == side and l['status'] == 'mustered' and (at is None or l['location'] == at)}

def force_n(l):
    return sum(l.get('forces', {}).values())

def feed_n(l):
    return math.ceil(force_n(l) / 6)

def goal(lid):
    l = s['lords'][lid]
    side = l['side']
    loc = l['location']
    if lid == 'provenzano' and s['lords']['siena']['status'] == 'mustered' and (s['lords']['siena']['location'] == loc):
        return goal('siena')
    if lid == 'astimberg' and s['lords']['giordano']['status'] == 'mustered' and (s['lords']['giordano']['location'] == loc):
        return goal('giordano')
    if l['assets'].get('Coin', 0) < (2 if l.get('podesta') else 1) and (l.get('service_box') or 99) <= s['meta']['turn'] + 1:
        seats = [n for n in l['seats'] if friendly(n, side) and (not s['locales'][n].get('siege'))]
        if seats:
            return min(seats, key=lambda n: distance(loc, n))
    for target in orders.get(lid, []):
        if target in s['locales'] and (not friendly(target, side)) and (not s['locales'][target].get('ruins')):
            return target
    candidates = [n for n, v in s['locales'].items() if not friendly(n, side) and v['type'] in ('castle', 'town') and (not v.get('ruins'))]
    return min(candidates, key=lambda n: distance(loc, n)) if candidates else loc

def select(ms, predicate):
    return [m for m in ms if predicate(m)]

def upkeep_choice(ms):
    """Pay before expiration, prefer Loot when actually allowed."""
    pays = [m for m in ms if m['action'] in ('cmd_fpd_pay', 'levy_pay')]
    urgent = [m for m in pays if (s['lords'][m['args']['target_lord_id']].get('service_box') or 99) <= s['meta']['turn']]
    if urgent:
        urgent.sort(key=lambda m: (m['args'].get('asset') != 'Loot', s['lords'][m['args']['target_lord_id']].get('service_box', 99), not s['lords'][m['args']['target_lord_id']].get('commander')))
        return (urgent[0], 'Preserve an expiring Lord with an available legal payment.')
    return (next((m for m in ms if m['action'].endswith('pay_done'))), 'Retain resources; no currently expiring Lord can or needs to be paid.')

def campaign_choice(ms):
    names = {m['action'] for m in ms}
    if 'cmd_fpd_pay_done' in names:
        return upkeep_choice(ms)
    if 'cmd_resolve_revolt' in names:
        choices = [m for m in ms if m['action'] == 'cmd_resolve_revolt']

        def key(m):
            n = m['args']['choice']
            v = s['locales'][n]
            side = m['side']
            near = min((distance(l['location'], n) for l in own_lords(side).values()), default=99)
            return (sd.STRONGHOLDS.get(v['type'], {}).get('size', 1), -near)
        return (max(choices, key=key), 'Resolve the political gain at a valuable, supportable Stronghold.')
    if 'cmd_resolve_exiles' in names:
        shifts = [m for m in ms if m.get('args', {}).get('slides')]
        if shifts:

            def key(m):
                x = m['args']['slides'][0]
                l = s['lords'][x['lord_id']]
                return (l['status'] == 'mustered' and (l.get('service_box') or 99) <= s['meta']['turn'] + 2, l['status'] == 'mustered', -(l.get('calendar_box') or 99))
            return (max(shifts, key=key), 'Use an Exiles shift to sustain an army or bring reinforcement closer.')
        return (ms[0], 'No useful eligible Exiles shift remains.')
    if 'approach_response' in names:
        p = next((p for p in s['pending'] if p['type'] == 'approach_response'))
        loc = p['info']['locale']
        side = p['side']
        own = sum((force_n(l) for l in own_lords(side, loc).values()))
        en = sum((force_n(l) for l in s['lords'].values() if l['status'] == 'mustered' and l['side'] != side and (l['location'] == loc)))
        ev = [m for m in ms if m['action'] == 'play_event' and m['side'] == side]
        if ev:
            return (ev[0], 'Use a held defensive event in the actual battle window.')
        responses = [m for m in ms if m['action'] == 'approach_response']
        if own >= en * 0.8:
            stands = [m for m in responses if m['args']['choice'] == 'stand']
            if stands:
                return (stands[0], 'Stand with comparable forces; the default combat resolver chooses within-battle details.')
        avoids = [m for m in responses if m['args']['choice'] == 'avoid']
        if avoids:
            return (min(avoids, key=lambda m: distance(m['args']['destination'], s['lords'][m['args']['lord_id']]['seats'][0])), 'Avoid a substantially stronger army and fall toward a friendly seat.')
        withdraw = [m for m in responses if m['args']['choice'] == 'withdraw']
        if withdraw:
            return (withdraw[0], 'Use the Stronghold rather than accept an unfavorable field battle.')
        return (responses[0], 'Resolve the available approach response.')
    if 'besiege_or_bypass' in names:
        ev = [m for m in ms if m['action'] == 'play_event' and m['args']['card_id'] in ('F3', 'S3')]
        if ev:
            lid = s['current_lord_id']
            l = s['lords'][lid]
            if force_n(l) >= 6:
                return (ev[0], 'Use Surprise with the prepared solo assault contingent.')
        return (next((m for m in ms if m['action'] == 'besiege_or_bypass' and m['args']['choice'] == 'besiege')), 'Besiege the objective rather than leave an uncontrolled Stronghold behind.')
    if 'command_reveal' in names:
        return (next((m for m in ms if m['action'] == 'command_reveal')), 'Reveal next planned activation.')
    lid = s.get('current_lord_id')
    if not lid:
        return None
    l = s['lords'][lid]
    side = l['side']
    loc = l['location']
    local = own_lords(side, loc)
    food = sum((v['assets'].get('Provender', 0) for v in local.values()))
    need = sum((feed_n(v) for v in local.values()))
    end = next((m for m in ms if m['action'] == 'cmd_end_card'), None)
    supplies = [m for m in ms if m['action'] == 'cmd_supply']
    if (s.get('current_card') or '').startswith('treachery_'):
        opts = [m for m in ms if m['action'] == 'cmd_treachery_revolt']
        if opts:
            return (max(opts, key=lambda m: sd.STRONGHOLDS[s['locales'][m['args']['target_locale']]['type']]['size']), 'Spend the planned Treachery card on a legal political objective.')
        opts = [m for m in ms if m['action'] == 'cmd_treachery_bribe']
        if opts:
            return (opts[0], 'Use otherwise idle Treachery to acquire enemy troops.')
        return (end, 'No eligible political target remains; let Treachery lapse.')
    target = goal(lid)
    if l.get('flags', {}).get('in_stronghold'):
        defenses = [m for m in ms if m['action'] in ('cmd_guastatori_pass', 'cmd_war_engineers_reduce')]
        if defenses:
            return (defenses[0], 'Use defensive engineers to delay the besiegers.')
        if supplies:
            return (max(supplies, key=lambda m: m['args']['provender']), 'Supply the besieged garrison legally.')
        forage = [m for m in ms if m['action'] == 'cmd_forage']
        if forage:
            return (forage[0], 'Feed the besieged Lord when the rules allow Forage.')
        sally = [m for m in ms if m['action'] == 'cmd_sally']
        if sally:
            return (sally[0], 'Attempt a Sally rather than allow an unsupplied siege to expire Service.')
        return (end, 'No safe action is available while besieged.')
    siege = [m for m in ms if m['action'] == 'cmd_siege']
    if siege and food >= need:
        return (siege[0], 'Attempt surrender and increase Siegeworks while the army can be fed.')
    if supplies and food < max(need * 2, 3):
        return (max(supplies, key=lambda m: m['args']['provender']), 'Replenish food before further movement or siege work.')
    tax = [m for m in ms if m['action'] == 'cmd_tax' and (not m.get('args', {}).get('reinforced_walls'))]
    if tax and l['assets'].get('Coin', 0) < 4:
        return (tax[0], 'Build Coin reserves at a legal Seat to pay for future Service.')
    if siege or s['locales'][loc].get('siege'):
        if supplies and food < need * 3:
            return (max(supplies, key=lambda m: m['args']['provender']), 'Use the logistics activation to replenish the besieging force.')
        return (end, 'Hold the siege; an entire-card Siege must wait for the next activation.')
    marches = [m for m in ms if m['action'] == 'cmd_march']
    toward = [m for m in marches if distance(m['args']['destination'], target) < distance(loc, target)]
    if toward:

        def key(m):
            group = m['args'].get('with_lords', [])
            return (-distance(m['args']['destination'], target), len(group), m['args'].get('way_type') == 'road')
        return (max(toward, key=key), f'Move toward the assigned objective {target}, preserving a legal group when possible.')
    if supplies and food < need * 2:
        return (max(supplies, key=lambda m: m['args']['provender']), 'Resupply while movement is unavailable.')
    forage = [m for m in ms if m['action'] == 'cmd_forage']
    if forage and food < need:
        return (forage[0], 'Forage to avoid an imminent Service penalty.')
    walls = [m for m in ms if m['action'] == 'cmd_tax' and m.get('args', {}).get('reinforced_walls')]
    if walls:
        return (walls[0], 'Fortify an exposed Seat rather than waste the activation.')
    if tax:
        return (tax[0], 'Bank Coin while the route is unavailable.')
    return (end, 'Do not invent a legal move or march aimlessly when the objective is inaccessible.') if end else None
CAP_PRIORITIES = {'War Engineers': 85, 'Stores & Well Water': 80, 'Guastatori': 72, 'Balestrieri': 61, 'Palvesari': 62, 'Balestre Grosse': 58, 'La Cavallata': 56, 'Via Francigena': 60, 'Astrologers': 53, 'Reinforced Walls': 45, 'Manfredi': 40, 'Costruttori': 35}

def muster_choice(ms):
    side = s['meta']['active_player']
    own = own_lords(side)
    ordinary = [v for v in own.values() if not v.get('comune_of')]
    sidecaps = [c for c in s['capabilities_in_play'] if c['side'] == side]
    scored = []
    for m in ms:
        a = m.get('args', {})
        act = m['action']
        score = -999
        l = s['lords'].get(a.get('lord_id'), {})
        if act == 'levy_muster_lord':
            target = s['lords'][a['target_lord_id']]
            score = 115 if target.get('commander') else 103 if len(ordinary) < 3 else 75 if len(ordinary) < 5 else 35
            score += target['ratings'].get('F', 0)
            score -= distance(a['target_seat'], goal(a['muster_lord_id'])) * 0.02
        elif act == 'levy_muster_transport':
            asset = 'Ship' if a['kind'] == 'Ship' else 'Cart'
            n = l.get('assets', {}).get(asset, 0)
            score = (79 if n < 4 else 48 if n < 6 else -999) if asset == 'Cart' else 50 if n < 4 else -999
        elif act == 'levy_muster_vassal':
            score = 68 if force_n(l) < 6 else 55 if force_n(l) < 9 else -999
        elif act == 'levy_muster_capability':
            c = cd.AOW_CARDS_BY_ID[a['card_id']]
            name = c['capability_name']
            scope = a['scope']
            heldnames = [cd.AOW_CARDS_BY_ID[x]['capability_name'] for x in l.get('capabilities', [])]
            sidenames = [x['name'] for x in sidecaps]
            if name in heldnames or (scope == 'side_wide' and (name in sidenames or len(sidecaps) >= len(ordinary))):
                continue
            score = CAP_PRIORITIES.get(name, -999)
            if name == 'Palvesari' and l.get('forces', {}).get('Armigieri', 0) == 0:
                score = 20
            if name == 'War Engineers' and l.get('commander'):
                score = 55
        elif act == 'play_event' and a.get('effect_args', {}).get('mode') == 'lordship':
            score = 120
        if score > 0:
            scored.append((score, m))
    if scored:
        return (max(scored, key=lambda x: x[0])[1], 'Recruit ready support, then prioritize siege engineering, transport and sustainable troop strength.')
    return (next((m for m in ms if m['action'] == 'levy_muster_done')), 'Finish Muster when no remaining purchase fits the campaign priorities.')

def event_choice(ms):
    opts = [m for m in ms if m['action'] == 'levy_resolve_event']
    if not opts:
        return None

    def score(m):
        a = m['args'].get('effect_args', {})
        lid = a.get('target_lord_id', a.get('lord_id', a.get('target')))
        l = s['lords'].get(lid, {})
        return (l.get('status') == 'mustered', l.get('commander', False), len(l.get('forces', {})), a.get('mode') == 'shift')
    return (max(opts, key=score), 'Resolve the compulsory Event against the most consequential visible target.')
