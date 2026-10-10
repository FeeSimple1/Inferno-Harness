#!/usr/bin/env python3
"""Fresh deterministic-policy self-play; exercises optional Call to Arms.
No state editing, forced dice, disabled victory/Exhaustion, or future-roll lookahead.
Policy functions are retained from the recorded long-scenario playtest.
"""
import sys, json, argparse, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
from inferno import actions as ac, card_data as cd, static_data as sd
from inferno.scenarios import load_scenario
from inferno.actions import dispatch
from inferno.legal_moves import enumerate_legal
from inferno.invariants import check_all_invariants

# The strategic priorities below come from the earlier model-directed playtest.
# This standalone run uses those priorities automatically; it is not a new
# manually directed game or two independent blind agents.
import math
from collections import deque

# Orders are priorities, not changes to the scenario or victory rules.
orders = {
 'arezzo':['Cortona','Montepulciano','Asinalunga','San Quirico'],
 'firenze':['Poggio Bonizio','Casole','San Gimignano','Volterra'],
 'colle':['Casole','San Gimignano','Volterra'],
 'lucca':['Pontedera','Castelfiorentino','Volterra'],
 'guido_guerra':['Vernio','Cantagallo','Montemurlo'],
 'orvieto':['Montepulciano','San Quirico','Radicofani'],
 'siena':['Montalcino','Montepulciano','Volterra','Colle'],
 'provenzano':['Montalcino','Montepulciano','Volterra','Colle'],
 'santa_fiora':['Grosseto','Montemassi','Montepescali','Montalcino'],
 'giordano':['Casole','Colle','Poggio Bonizio'],
 'astimberg':['Casole','Colle','Poggio Bonizio'],
 'pisa':['Pontedera','San Miniato','Lucca'],
}

def friendly(name,side):
    return ac._is_friendly_locale(s,s['locales'][name],side)

def distance(a,b):
    if a==b:return 0
    q=deque([(a,0)]);seen={a}
    while q:
        n,d=q.popleft()
        for nn,_ in sd.adjacent_to(n):
            if nn==b:return d+1
            if nn not in seen:seen.add(nn);q.append((nn,d+1))
    return 999

def own_lords(side,at=None):
    return {k:l for k,l in s['lords'].items() if l['side']==side and l['status']=='mustered'
            and (at is None or l['location']==at)}

def force_n(l):return sum(l.get('forces',{}).values())
def feed_n(l):return math.ceil(force_n(l)/6)

def goal(lid):
    l=s['lords'][lid];side=l['side'];loc=l['location']
    # A commander keeps his colleague's accompanying force on the same mission.
    if lid=='provenzano' and s['lords']['siena']['status']=='mustered' and s['lords']['siena']['location']==loc:
        return goal('siena')
    if lid=='astimberg' and s['lords']['giordano']['status']=='mustered' and s['lords']['giordano']['location']==loc:
        return goal('giordano')
    # Return to a tax seat when reserves will not fund another service extension.
    if l['assets'].get('Coin',0)<(2 if l.get('podesta') else 1) and (l.get('service_box') or 99)<=s['meta']['turn']+1:
        seats=[n for n in l['seats'] if friendly(n,side) and not s['locales'][n].get('siege')]
        if seats:return min(seats,key=lambda n:distance(loc,n))
    for target in orders.get(lid,[]):
        if target in s['locales'] and not friendly(target,side) and not s['locales'][target].get('ruins'):
            return target
    # Prioritize accessible enemy castles/towns, not a suicidal capital attack.
    candidates=[n for n,v in s['locales'].items() if not friendly(n,side)
                and v['type'] in ('castle','town') and not v.get('ruins')]
    return min(candidates,key=lambda n:distance(loc,n)) if candidates else loc

def select(ms, predicate):
    return [m for m in ms if predicate(m)]

def upkeep_choice(ms):
    """Pay before expiration, prefer Loot when actually allowed."""
    pays=[m for m in ms if m['action'] in ('cmd_fpd_pay','levy_pay')]
    urgent=[m for m in pays if (s['lords'][m['args']['target_lord_id']].get('service_box') or 99)<=s['meta']['turn']]
    if urgent:
        urgent.sort(key=lambda m:(m['args'].get('asset')!='Loot',
                                 s['lords'][m['args']['target_lord_id']].get('service_box',99),
                                 not s['lords'][m['args']['target_lord_id']].get('commander')))
        return urgent[0],'Preserve an expiring Lord with an available legal payment.'
    return next(m for m in ms if m['action'].endswith('pay_done')),'Retain resources; no currently expiring Lord can or needs to be paid.'

def campaign_choice(ms):
    names={m['action'] for m in ms}
    if 'cmd_fpd_pay_done' in names:return upkeep_choice(ms)
    if 'cmd_resolve_revolt' in names:
        choices=[m for m in ms if m['action']=='cmd_resolve_revolt']
        # Choose the largest attainable allegiance swing; then nearest friendly forces.
        def key(m):
            n=m['args']['choice'];v=s['locales'][n];side=m['side']
            near=min((distance(l['location'],n) for l in own_lords(side).values()),default=99)
            return (sd.STRONGHOLDS.get(v['type'],{}).get('size',1),-near)
        return max(choices,key=key),'Resolve the political gain at a valuable, supportable Stronghold.'
    if 'cmd_resolve_exiles' in names:
        shifts=[m for m in ms if m.get('args',{}).get('slides')]
        if shifts:
            def key(m):
                x=m['args']['slides'][0];l=s['lords'][x['lord_id']]
                return (l['status']=='mustered' and (l.get('service_box') or 99)<=s['meta']['turn']+2,
                        l['status']=='mustered',-(l.get('calendar_box') or 99))
            return max(shifts,key=key),'Use an Exiles shift to sustain an army or bring reinforcement closer.'
        return ms[0],'No useful eligible Exiles shift remains.'
    if 'approach_response' in names:
        p=next(p for p in s['pending'] if p['type']=='approach_response')
        loc=p['info']['locale'];side=p['side']
        own=sum(force_n(l) for l in own_lords(side,loc).values())
        en=sum(force_n(l) for l in s['lords'].values() if l['status']=='mustered' and l['side']!=side and l['location']==loc)
        # Consume an applicable combat card before resolving the Approach.
        ev=[m for m in ms if m['action']=='play_event' and m['side']==side]
        if ev:return ev[0],'Use a held defensive event in the actual battle window.'
        responses=[m for m in ms if m['action']=='approach_response']
        if own>=en*.8:
            stands=[m for m in responses if m['args']['choice']=='stand']
            if stands:return stands[0],'Stand with comparable forces; the default combat resolver chooses within-battle details.'
        avoids=[m for m in responses if m['args']['choice']=='avoid']
        if avoids:return min(avoids,key=lambda m:distance(m['args']['destination'],s['lords'][m['args']['lord_id']]['seats'][0])), 'Avoid a substantially stronger army and fall toward a friendly seat.'
        withdraw=[m for m in responses if m['args']['choice']=='withdraw']
        if withdraw:return withdraw[0],'Use the Stronghold rather than accept an unfavorable field battle.'
        return responses[0],'Resolve the available approach response.'
    if 'besiege_or_bypass' in names:
        ev=[m for m in ms if m['action']=='play_event' and m['args']['card_id'] in ('F3','S3')]
        if ev:
            lid=s['current_lord_id'];l=s['lords'][lid]
            if force_n(l)>=6:return ev[0],'Use Surprise with the prepared solo assault contingent.'
        return next(m for m in ms if m['action']=='besiege_or_bypass' and m['args']['choice']=='besiege'), 'Besiege the objective rather than leave an uncontrolled Stronghold behind.'
    if 'command_reveal' in names:return next(m for m in ms if m['action']=='command_reveal'),'Reveal next planned activation.'
    lid=s.get('current_lord_id')
    if not lid:return None
    l=s['lords'][lid];side=l['side'];loc=l['location'];local=own_lords(side,loc)
    food=sum(v['assets'].get('Provender',0) for v in local.values())
    need=sum(feed_n(v) for v in local.values())
    end=next((m for m in ms if m['action']=='cmd_end_card'),None)
    supplies=[m for m in ms if m['action']=='cmd_supply']
    if (s.get('current_card') or '').startswith('treachery_'):
        opts=[m for m in ms if m['action']=='cmd_treachery_revolt']
        if opts:return max(opts,key=lambda m:sd.STRONGHOLDS[s['locales'][m['args']['target_locale']]['type']]['size']), 'Spend the planned Treachery card on a legal political objective.'
        opts=[m for m in ms if m['action']=='cmd_treachery_bribe']
        if opts:return opts[0],'Use otherwise idle Treachery to acquire enemy troops.'
        return end,'No eligible political target remains; let Treachery lapse.'
    target=goal(lid)
    if l.get('flags',{}).get('in_stronghold'):
        defenses=[m for m in ms if m['action'] in ('cmd_guastatori_pass','cmd_war_engineers_reduce')]
        if defenses:return defenses[0],'Use defensive engineers to delay the besiegers.'
        if supplies:return max(supplies,key=lambda m:m['args']['provender']),'Supply the besieged garrison legally.'
        forage=[m for m in ms if m['action']=='cmd_forage']
        if forage:return forage[0],'Feed the besieged Lord when the rules allow Forage.'
        sally=[m for m in ms if m['action']=='cmd_sally']
        if sally:return sally[0],'Attempt a Sally rather than allow an unsupplied siege to expire Service.'
        return end,'No safe action is available while besieged.'
    siege=[m for m in ms if m['action']=='cmd_siege']
    if siege and food>=need:
        return siege[0],'Attempt surrender and increase Siegeworks while the army can be fed.'
    if supplies and food<max(need*2,3):
        # This rule avoids looking at any future draw, combat, or surrender roll.
        return max(supplies,key=lambda m:m['args']['provender']), 'Replenish food before further movement or siege work.'
    tax=[m for m in ms if m['action']=='cmd_tax' and not m.get('args',{}).get('reinforced_walls')]
    if tax and l['assets'].get('Coin',0)<4:
        return tax[0],'Build Coin reserves at a legal Seat to pay for future Service.'
    # Do not March just to spend leftover actions after a resupply at a live siege.
    if siege or s['locales'][loc].get('siege'):
        if supplies and food<need*3:return max(supplies,key=lambda m:m['args']['provender']), 'Use the logistics activation to replenish the besieging force.'
        return end,'Hold the siege; an entire-card Siege must wait for the next activation.'
    marches=[m for m in ms if m['action']=='cmd_march']
    toward=[m for m in marches if distance(m['args']['destination'],target)<distance(loc,target)]
    if toward:
        def key(m):
            group=m['args'].get('with_lords',[])
            return (-distance(m['args']['destination'],target),len(group),m['args'].get('way_type')=='road')
        return max(toward,key=key),f'Move toward the assigned objective {target}, preserving a legal group when possible.'
    if supplies and food<need*2:return max(supplies,key=lambda m:m['args']['provender']), 'Resupply while movement is unavailable.'
    forage=[m for m in ms if m['action']=='cmd_forage']
    if forage and food<need:return forage[0],'Forage to avoid an imminent Service penalty.'
    # Counterfortification is useful when holding an exposed Seat.
    walls=[m for m in ms if m['action']=='cmd_tax' and m.get('args',{}).get('reinforced_walls')]
    if walls:return walls[0],'Fortify an exposed Seat rather than waste the activation.'
    if tax:return tax[0],'Bank Coin while the route is unavailable.'
    return (end,'Do not invent a legal move or march aimlessly when the objective is inaccessible.') if end else None

# Recruitment/refit assistance: prioritize maintaining a playable army, then
# engineering and transport. Stop at Call to Arms so the assistant reviews it.
CAP_PRIORITIES={'War Engineers':85,'Stores & Well Water':80,'Guastatori':72,
                'Balestrieri':61,'Palvesari':62,'Balestre Grosse':58,
                'La Cavallata':56,'Via Francigena':60,'Astrologers':53,
                'Reinforced Walls':45,'Manfredi':40,'Costruttori':35}

def muster_choice(ms):
    side=s['meta']['active_player'];own=own_lords(side)
    ordinary=[v for v in own.values() if not v.get('comune_of')]
    sidecaps=[c for c in s['capabilities_in_play'] if c['side']==side]
    scored=[]
    for m in ms:
        a=m.get('args',{});act=m['action'];score=-999
        l=s['lords'].get(a.get('lord_id'),{})
        if act=='levy_muster_lord':
            target=s['lords'][a['target_lord_id']]
            score=(115 if target.get('commander') else 103 if len(ordinary)<3 else 75 if len(ordinary)<5 else 35)
            score+=target['ratings'].get('F',0)
            score-=distance(a['target_seat'],goal(a['muster_lord_id']))*.02
        elif act=='levy_muster_transport':
            asset='Ship' if a['kind']=='Ship' else 'Cart'
            n=l.get('assets',{}).get(asset,0)
            score=(79 if n<4 else 48 if n<6 else -999) if asset=='Cart' else (50 if n<4 else -999)
        elif act=='levy_muster_vassal':
            score=68 if force_n(l)<6 else 55 if force_n(l)<9 else -999
        elif act=='levy_muster_capability':
            c=cd.AOW_CARDS_BY_ID[a['card_id']];name=c['capability_name'];scope=a['scope']
            # Avoid picking duplicate named Capabilities already on this mat/side.
            heldnames=[cd.AOW_CARDS_BY_ID[x]['capability_name'] for x in l.get('capabilities',[])]
            sidenames=[x['name'] for x in sidecaps]
            if name in heldnames or (scope=='side_wide' and (name in sidenames or len(sidecaps)>=len(ordinary))):continue
            score=CAP_PRIORITIES.get(name,-999)
            if name=='Palvesari' and l.get('forces',{}).get('Armigieri',0)==0:score=20
            if name=='War Engineers' and l.get('commander'):score=55
        elif act=='play_event' and a.get('effect_args',{}).get('mode')=='lordship':
            score=120
        if score>0:scored.append((score,m))
    if scored:
        return max(scored,key=lambda x:x[0])[1],'Recruit ready support, then prioritize siege engineering, transport and sustainable troop strength.'
    return next(m for m in ms if m['action']=='levy_muster_done'),'Finish Muster when no remaining purchase fits the campaign priorities.'

def event_choice(ms):
    opts=[m for m in ms if m['action']=='levy_resolve_event']
    if not opts:return None
    # Required choices are ranked on visible state, never a sampled outcome.
    def score(m):
        a=m['args'].get('effect_args',{});lid=a.get('target_lord_id',a.get('lord_id',a.get('target')))
        l=s['lords'].get(lid,{})
        return (l.get('status')=='mustered',l.get('commander',False),
                len(l.get('forces',{})),a.get('mode')=='shift')
    return max(opts,key=score),'Resolve the compulsory Event against the most consequential visible target.'


def policy_plan(side):
    slots=sd.PLAN_SIZE_BY_SEASON[sd.SEASON_BY_BOX[s['meta']['turn']]]
    ordinary=[(lid,l) for lid,l in own_lords(side).items() if not l.get('comune_of')]
    def urgency(item):
        lid,l=item; loc=l['location']; t=s['meta']['turn']
        cost=2 if l.get('podesta') else 1
        u=3+int(l.get('commander',False))
        if s['locales'][loc].get('siege'):u+=4
        if (l.get('service_box') or 99)<=t+1 and l['assets'].get('Coin',0)<cost*2:u+=5
        if loc in l['seats'] and l['assets'].get('Coin',0)<cost*2:u+=2
        return u
    ordered=sorted(ordinary,key=lambda x:(-urgency(x),x[0]))
    selected=[];counts={}
    # One activation per live Lord before extra cards, subject to seasonal limit.
    for lid,l in ordered[:slots]:
        selected.append(lid);counts[lid]=1
    while len(selected)<slots:
        candidates=[x for x in ordered if counts.get(x[0],0)<3]
        if not candidates: selected.append('PASS');continue
        lid,l=max(candidates,key=lambda x:urgency(x)-counts.get(x[0],0)*4)
        selected.append(lid);counts[lid]=counts.get(lid,0)+1
    return selected

def discard_choice(ms):
    done=[m for m in ms if m['action']=='campaign_discard_done']
    if done:return done[0]
    choices=[m for m in ms if m['action']=='campaign_discard_capability']
    return min(choices,key=lambda m:CAP_PRIORITIES.get(cd.AOW_CARDS_BY_ID[m['args']['card_id']]['capability_name'],0))



def choose_move(moves, plans):
    names={m['action'] for m in moves}
    if names & {'cmd_resolve_revolt','cmd_resolve_exiles','cmd_fpd_pay_done','approach_response','besiege_or_bypass'}:
        return campaign_choice(moves)[0]
    if s['meta']['phase']=='levy':
        step=s['meta']['levy_step']
        if step=='3.1':
            if 'levy_resolve_event' in names:return event_choice(moves)[0]
            return moves[0]
        if step=='3.2':return upkeep_choice(moves)[0]
        if step=='3.3':return next((m for m in moves if m['action']=='levy_disband'),moves[0])
        if step=='3.4' or s['meta'].get('cta_substep')=='allies_muster':return muster_choice(moves)[0]
        if step=='3.5':
            if not s['meta'].get('cta_active'):
                return next((m for m in moves if m['action']=='levy_cta_declare'),moves[0])
            sub=s['meta']['cta_substep'];side=s['meta']['active_player']
            skip=next(m for m in moves if m['action']=='cta_step_skip')
            if sub=='gather':return skip  # Voluntary: keep field armies in their current operations.
            if sub=='commander_arms':
                cmd=s['lords'][ac.COMMANDER_LORD[side]]
                if cmd['status']=='on_calendar':
                    return next((m for m in moves if m['action']=='cta_commander_arms' and m['args']['mode']=='muster_only'),skip)
                if cmd['location']!=ac.LEADING_CITY[side]:
                    return next((m for m in moves if m['action']=='cta_commander_arms' and m['args']['mode']=='disband_and_remuster'),skip)
                return skip
            if sub=='comune':
                options=[m for m in moves if m['action']=='cta_comune_setup']
                if not options:return skip
                if s['lords'][ac.COMUNE_LORD[side]]['status']=='mustered':
                    return next((m for m in options if len(m['args'].get('muster_special_vassals',[]))==1),options[0])
                return options[0]
            if sub=='allies':
                autos=[m for m in moves if m['action']=='cta_allies' and m['args']['mode']=='auto_muster']
                if autos and len([l for l in own_lords(side).values() if not l.get('comune_of')])<3:return autos[0]
                extras=[m for m in moves if m['action']=='cta_allies' and m['args']['mode']=='extra_muster']
                return next((m for m in extras if m['args']['target_lord_id']==ac.COMMANDER_LORD[side]),
                            extras[0] if extras else (autos[0] if autos else skip))
    step=s['meta'].get('campaign_step')
    if step=='capability_discard':return discard_choice(moves)
    if step=='plan':
        done=next((m for m in moves if m['action']=='plan_done'),None)
        if done:return done
        side=s['meta']['active_player'];key=(s['meta']['turn'],side)
        if key not in plans:plans[key]=policy_plan(side)
        cid=plans[key][len(s['plan_stacks'][side])]
        cid='PASS' if cid=='PASS' else 'command_'+cid
        return next((m for m in moves if m['action']=='plan_add_card' and m['args']['card_id']==cid),
                    next(m for m in moves if m['action']=='plan_add_card' and m['args']['card_id']=='PASS'))
    if step=='command_phase':return campaign_choice(moves)[0]
    if step=='end_campaign':return moves[0]
    raise RuntimeError(f'Unhandled decision: {s["meta"]}')


def main():
    global s
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=20261010)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    s=load_scenario('F',seed=args.seed,hidden_mats=False,advanced_vassal_service=False)
    plans={};rows=[];counts=collections.Counter();error=None
    try:
        for _ in range(8000):
            if s['meta'].get('game_over'):break
            moves=enumerate_legal(s)
            assert moves,'Empty legal menu before game end'
            chosen=choose_move(moves,plans)
            action={k:chosen[k] for k in ('action','side','args') if k in chosen}
            step=s['meta'].get('cta_substep')
            result=dispatch(s,action)
            rows.append({'action':action,'result':result,'turn':s['meta']['turn']})
            counts[action['action']]+=1
            if step=='allies_muster' and action['action'].startswith('levy_muster_'):
                counts['extra_segment_'+action['action']]+=1
            check_all_invariants(s)
            for cid in ('firenze_comune','siena_comune'):
                comune=s['lords'][cid]
                if comune['status']=='mustered':
                    commander=s['lords'][ac.COMMANDER_LORD[comune['side']]]
                    assert commander['status']=='mustered' and commander['location']==comune['location'],f'Separated {cid}'
        assert s['meta'].get('game_over'),'Did not complete within step budget'
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
    args.output.mkdir(parents=True,exist_ok=True)
    summary={'seed':args.seed,'actions':len(rows),'turn':s['meta']['turn'],
             'winner':s['meta'].get('winner'),'game_over':s['meta'].get('game_over'),
             'vp':s['vp'],'counts':dict(counts),'error':error}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (args.output/'actions_and_results.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
    (args.output/'final_state.json').write_text(json.dumps(s,separators=(',',':'))+'\n')
    print(json.dumps(summary,indent=2))
    if error:raise RuntimeError(error)

if __name__=='__main__':main()
