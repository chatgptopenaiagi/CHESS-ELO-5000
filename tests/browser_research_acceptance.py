"""Read-only live research UI acceptance for an already completed frozen-source run.

This script creates no experiment, tournament, move, analysis or learning job.
It signs in, reads the accepted jobs, inspects actual rendered evidence and reloads.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
from browser_acceptance import Acceptance

ROOT=Path(__file__).resolve().parents[1]
METHODS={'conventional','uniform','heuristic','learned'}

def result_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def accepted(records,identity):
    rows=[r for r in records if str(r.get('status','')).lower()=='completed' and r.get('result')]
    if identity:rows=[r for r in rows if r['id']==identity]
    if not rows:raise AssertionError('Requested completed research job is unavailable to this owner')
    return rows[0]

def research(h,context,args):
    page=h.watch(context.new_page());h.signin_standalone(page)
    before_experiments=h.get(page,'/research/experiments')['experiments']
    before_tournaments=h.get(page,'/tournaments')['tournaments']
    experiment=accepted(before_experiments,args.experiment_id)
    tournament=accepted(before_tournaments,args.tournament_id)
    result=experiment['result'];tournament_result=tournament['result']
    for name,value in (('relevance experiment',result),('paired tournament',tournament_result)):
        source=value.get('source',{})
        h.check('Accepted '+name+' belongs to frozen source commit',source.get('commit')==args.expected_commit and not source.get('dirty',False),source_commit=source.get('commit'))
    h.check('Experiment contains all four actual search methods',set(result['summary'])==METHODS)
    h.check('Held-out comparisons record all four methods',METHODS <= {r['policy'] for r in result['comparisons']})
    model=result['model'];model_id=model['model_id']
    h.check('Learned policy is frozen with a stable model identity',model.get('frozen') is True and len(model_id)==64,model_id=model_id)
    h.navigate(page,'research')
    title='Experiment '+experiment['id'][:12]
    card=page.locator('article.card.study-detail').filter(has=page.get_by_role('heading',name=title,exact=True))
    card.wait_for(state='visible')
    summary=card.locator('table').first
    h.check('Research dashboard renders four measured method rows',summary.locator('tbody tr').count()==4)
    text=summary.inner_text()
    for phrase in ('Conventional engine','Uniform allocation','Heuristic relevance','Learned relevance'):
        h.check('Dashboard exposes '+phrase,phrase in text)
    card.get_by_text('Compare individual held-out positions',exact=True).click()
    h.check('Dashboard comparison table displays actual held-out evidence',card.locator('table').nth(1).locator('tbody tr').count()==len(result['comparisons']))
    evidence=card.locator('details').filter(has=page.get_by_text('Inspect full recorded research evidence',exact=True))
    evidence.locator('summary').click()
    h.check('Dashboard exposes the exact frozen model ID in its evidence inspector',evidence.locator('pre').is_visible() and model_id in evidence.locator('pre').inner_text())
    evidence.locator('summary').click()
    h.screenshot(page,'accepted-prospective-relevance-dashboard')
    h.navigate(page,'tournaments')
    title='Tournament '+tournament['id'][:12]
    card=page.locator('article.card.study-detail').filter(has=page.get_by_role('heading',name=title,exact=True));card.wait_for(state='visible')
    games=tournament_result['games']
    h.check('Tournament dashboard renders actual paired game results',len(games)>=2 and card.locator('table tbody tr').count()==len(games))
    h.check('Paired evidence includes reversed colors',{g['color_reversed'] for g in games}=={False,True})
    h.check('Reported wins draws losses account for completed games',sum(tournament_result[k] for k in ('wins','draws','losses'))==tournament_result['games_completed'])
    h.screenshot(page,'accepted-paired-tournament-dashboard')
    experiment_hash=result_digest(result);tournament_hash=result_digest(tournament_result)
    page.reload(wait_until='networkidle')
    page.wait_for_function("document.querySelector('#breadcrumb').textContent==='Tournaments'")
    after_experiments=h.get(page,'/research/experiments')['experiments'];after_tournaments=h.get(page,'/tournaments')['tournaments']
    reloaded_experiment=accepted(after_experiments,experiment['id']);reloaded_tournament=accepted(after_tournaments,tournament['id'])
    h.check('Page reload preserves exact accepted experiment identity and results',result_digest(reloaded_experiment['result'])==experiment_hash,experiment_id=experiment['id'],result_sha256=experiment_hash)
    h.check('Page reload preserves exact paired tournament identity and results',result_digest(reloaded_tournament['result'])==tournament_hash,tournament_id=tournament['id'],result_sha256=tournament_hash)
    h.check('Research browser navigation creates no expensive jobs',{r['id'] for r in after_experiments}=={r['id'] for r in before_experiments} and {r['id'] for r in after_tournaments}=={r['id'] for r in before_tournaments})
    h.navigate(page,'research');page.get_by_role('heading',name='Experiment '+experiment['id'][:12],exact=True).wait_for(state='visible')
    h.check('Reloaded dashboard presents the same accepted experiment',page.get_by_role('heading',name='Experiment '+experiment['id'][:12],exact=True).count()==1)
    h.screenshot(page,'reloaded-accepted-research-dashboard')
    (h.out/'accepted-identities.json').write_text(json.dumps({'source_commit':args.expected_commit,'experiment_id':experiment['id'],'experiment_result_sha256':experiment_hash,'model_id':model_id,'tournament_id':tournament['id'],'tournament_result_sha256':tournament_hash,'expensive_jobs_created':0},indent=2),encoding='utf-8')
    page.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--experiment-id')
    parser.add_argument('--tournament-id')
    parser.add_argument('--backend',default='http://127.0.0.1:18961')
    parser.add_argument('--joomla',default='http://127.0.0.1:18952')
    parser.add_argument('--edge',default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args=parser.parse_args();args.phase='research';args.package=str(ROOT/'dist/CHESS-ELO-5000-Joomla-Package.zip')
    h=Acceptance(args)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=args.edge,headless=True);h.browser_version=browser.version
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            h.scenario('accepted_research_ui',lambda:research(h,context,args))
            context.close();browser.close()
        h.check('No uncaught research browser JavaScript errors',not h.errors,errors=h.errors)
    except Exception as exc:h.cases.append(dict(name='research_browser_completion',status='FAIL',error=h.redact(f'{type(exc).__name__}: {exc}')))
    sys.exit(0 if h.report() else 1)

if __name__=='__main__':main()
