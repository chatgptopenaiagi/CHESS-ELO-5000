"""Live Edge acceptance. Uses the installed Edge binary; never downloads a browser.

Run --phase before-restart, restart the owned backend, then --phase after-restart.
Credentials and browser cookies remain in runtime/private and never enter evidence.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import chess
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
START = chess.STARTING_FEN
PROMOTION = '7k/P7/8/8/8/8/8/7K w - - 0 1'

class Acceptance:
    def __init__(self, args):
        self.args=args
        self.private=ROOT/'runtime/private'
        self.config=json.loads((self.private/'config.json').read_text(encoding='utf-8-sig'))
        self.access=json.loads((self.private/'joomla-access.json').read_text(encoding='utf-8-sig'))
        self.secrets=[str(v) for cfg in (self.config,self.access) for k,v in cfg.items() if ('password' in k or 'secret' in k) and v]
        self.stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.out=ROOT/'evidence/browser'/f'{self.stamp}-{args.phase}'
        self.out.mkdir(parents=True,exist_ok=True)
        self.cases=[];self.errors=[];self.checkpoint={};self.page=None;self.package_tested_sha256=None
    def redact(self,text):
        value=str(text)
        for secret in self.secrets:value=value.replace(secret,'[REDACTED]')
        return value
    def check(self,name,condition=True,**details):
        self.cases.append(dict(name=name,status='PASS' if condition else 'FAIL',**details))
        if not condition:raise AssertionError(name)
    def screenshot(self,page,name):
        page.screenshot(path=str(self.out/f'{name}.png'),full_page=True)
    def scenario(self,name,fn):
        try:fn()
        except Exception as exc:
            self.cases.append(dict(name=name,status='FAIL',error=self.redact(f'{type(exc).__name__}: {exc}')))
            if self.page and not self.page.is_closed() and not self.page.locator('input[type=password]:visible').count():
                try:self.screenshot(self.page,name+'-failure')
                except Exception:pass
    def watch(self,page):
        self.page=page
        page.set_default_timeout(20000)
        page.on('pageerror',lambda error:self.errors.append(self.redact(str(error))))
        page.on('dialog',lambda dialog:dialog.accept())
        return page
    def get(self,page,path):
        result=page.evaluate("""async path=>{
          const c=window.CHESS_CONFIG||{};
          const url=c.proxy?c.apiBase+encodeURIComponent('/api/v1'+path):(c.apiBase||'/api/v1')+path;
          const response=await fetch(url,{credentials:'same-origin'});
          return {status:response.status,body:await response.json()};
        }""",path)
        if result['status']!=200:raise AssertionError(f'GET {path}: HTTP{result["status"]}')
        return result['body']
    def current(self,page):
        identity=page.evaluate("localStorage.getItem('chesselo5000.game')")
        if not identity:raise AssertionError('No current saved game identity')
        return self.get(page,'/games/'+identity)
    def legal_replay(self,game):
        board=chess.Board(game['starting_fen'])
        for row in game['moves']:
            move=chess.Move.from_uci(row['uci'])
            if move not in board.legal_moves:raise AssertionError('Saved game contains an illegal move')
            board.push(move)
            if board.fen()!=row['fen']:raise AssertionError('Saved move FEN differs from replay')
        if board.fen()!=game['fen']:raise AssertionError('Final board differs from deterministic replay')
        return board
    def signin_standalone(self,page):
        page.goto(self.args.backend,wait_until='networkidle')
        page.locator('#account-button').click()
        page.locator('#owner-password').fill(self.config['owner_password'])
        page.locator('#login-form button[type=submit]').click()
        page.locator('#login-dialog').wait_for(state='hidden')
        page.wait_for_function("document.querySelector('#account-button').textContent!=='Sign in'")
        self.check('Standalone real owner sign-in')
    def new_game(self,page,mode='human',color='white',fen=''):
        page.locator('#new-game-button').click()
        page.locator('#new-mode').select_option(mode)
        page.locator('#new-color').select_option(color)
        page.locator('#new-time').select_option('0')
        page.locator('#new-increment').fill('0')
        page.locator('#engine-time').select_option('300')
        if fen or page.locator('#new-fen').input_value():
            if not page.locator('#new-fen').is_visible():page.locator('#new-game-form details summary').click()
            page.locator('#new-fen').fill(fen)
        page.locator('#new-game-form button[type=submit]').click()
        page.locator('#new-game-dialog').wait_for(state='hidden')
        page.wait_for_function("document.querySelector('#game-mode-label').textContent!=='READY WHEN YOU ARE'")
        return self.current(page)
    def move(self,page,uci,count):
        page.locator(f'[data-square="{uci[:2]}"]').click()
        self.check('Legal destination highlighted '+uci,page.locator(f'[data-square="{uci[2:4]}"].legal').count()==1)
        page.locator(f'[data-square="{uci[2:4]}"]').click()
        if len(uci)==5:page.locator(f'[data-promotion="{uci}"]').click()
        page.wait_for_function('(n)=>document.querySelectorAll("#move-history [data-ply]").length>=n',arg=count)
    def navigate(self,page,view):
        if page.locator('#menu-toggle').is_visible():page.locator('#menu-toggle').click()
        page.locator(f'#navigation [data-view="{view}"]').click()
        page.wait_for_function('(v)=>document.querySelector("#breadcrumb").textContent===v',arg={'play':'Play chess','analysis':'Analysis board','archive':'Game archive','learn':'Learn & practice','puzzles':'Tactical puzzles','studies':'Opening & endgames','research':'Relevance lab','tournaments':'Tournaments'}[view])
    def standalone(self,context):
        page=self.watch(context.new_page());self.signin_standalone(page)
        self.check('Standalone renders 64 squares',page.locator('#chessboard .square').count()==64)
        self.new_game(page,'engine')
        self.move(page,'e2e4',2)
        first=self.current(page);self.legal_replay(first)
        self.check('Human click move followed by actual legal engine reply',len(first['moves'])==2 and first['moves'][0]['uci']=='e2e4')
        source=page.locator('[data-square="g1"]');source.scroll_into_view_if_needed()
        a=source.bounding_box();b=page.locator('[data-square="f3"]').bounding_box()
        page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
        page.mouse.down();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=12);page.mouse.up()
        page.wait_for_function('document.querySelectorAll("#move-history [data-ply]").length>=4')
        ongoing=self.current(page);self.legal_replay(ongoing)
        self.check('Human drag move followed by legal engine reply',ongoing['moves'][2]['uci']=='g1f3' and len(ongoing['moves'])==4)
        self.checkpoint['resumable_game']={k:ongoing[k] for k in ('id','fen','version','moves','turn','status','white_ms','black_ms')}
        self.screenshot(page,'standalone-human-engine')
        self.new_game(page,'engine','black')
        page.wait_for_function('document.querySelectorAll("#move-history [data-ply]").length>=1')
        self.move(page,'e7e5',3)
        black=self.current(page);self.legal_replay(black)
        self.check('Human Black and engine White genuinely play',black['human_color']=='black' and len(black['moves'])==3)
        self.new_game(page,'human')
        for count,uci in enumerate(('f2f3','e7e5','g2g4','d8h4'),1):self.move(page,uci,count)
        terminal=self.current(page);board=self.legal_replay(terminal)
        self.check('Complete standard-start game ends through checkmate',board.is_checkmate() and terminal['status']=='finished' and terminal['result']=='0-1')
        self.check('Terminal position highlights checked king',page.locator('.square.in-check').count()==1)
        self.checkpoint['terminal_game']={k:terminal[k] for k in ('id','fen','result','status','version','moves')}
        self.screenshot(page,'standalone-checkmate')
        self.navigate(page,'archive')
        with page.expect_download() as download_event:page.locator('[data-action="export-current"]').click()
        path=self.out/'complete-game.pgn';download_event.value.save_as(path);pgn=path.read_text(encoding='utf-8-sig')
        self.check('Browser PGN export contains complete terminal game','0-1' in pgn and 'Qh4#' in pgn)
        page.locator('[data-action="import-pgn"]').click();page.locator('#text-dialog-value').fill(pgn);page.locator('#text-dialog-submit').click();page.locator('#text-dialog').wait_for(state='hidden')
        imported=self.current(page);self.legal_replay(imported)
        self.check('PGN imports into separate study with exact final FEN',imported['id']!=terminal['id'] and imported['fen']==terminal['fen'] and len(imported['moves'])==4)
        self.checkpoint['imported_study']={k:imported[k] for k in ('id','fen','version','moves','status','result')}
        page.locator('[data-replay="previous"]').click()
        self.check('Archive replay selects penultimate saved position',page.locator('#replay-label').inner_text()=='PLY 3 / 4')
        page.locator('#branch-position').click();page.locator('#text-dialog-value').fill('d8f6');page.locator('#text-dialog-submit').click();page.locator('#text-dialog').wait_for(state='hidden')
        variations=self.get(page,'/games/'+imported['id']+'/variations')['variations']
        unchanged=self.get(page,'/games/'+terminal['id'])
        self.check('Alternative branch has ancestry and preserves historical game',len(variations)>=1 and unchanged['fen']==terminal['fen'] and unchanged['moves']==terminal['moves'])
        page.locator('#analysis-time').select_option('500');page.locator('#analyze-position').click()
        page.wait_for_function("['ANALYSIS COMPLETE','CACHED RESULT'].includes(document.querySelector('#engine-state').textContent)",timeout=30000)
        self.check('Browser displays real mate score and engine PV','M1' in page.locator('#analysis-results').inner_text() and 'Qh4#' in page.locator('#analysis-results').inner_text())
        page.locator('#coach-position').click();page.wait_for_function("document.querySelector('#coach-output').textContent.includes('ENGINE EVALUATION')")
        self.check('Deterministic coach consumes completed matching engine evidence','ENGINE EVALUATION' in page.locator('#coach-output').inner_text())
        self.screenshot(page,'standalone-mate-analysis-coach')
        self.new_game(page,'human',fen=PROMOTION)
        self.move(page,'a7a8q',1)
        promoted=self.current(page)
        self.check('Explicit promotion chooser submits selected queen',promoted['piece_map'].get('a8')=='Q' and promoted['moves'][0]['uci']=='a7a8q')
        self.navigate(page,'puzzles');page.locator('[data-start-exercise="scholar-mate"]').click();self.move(page,'h5f7',1);page.locator('#check-exercise').click()
        page.wait_for_function("document.querySelector('#coach-output').textContent.includes('Verified objective achieved')")
        self.check('Interactive puzzle solved and progress persisted',self.get(page,'/progress')['puzzles_solved']>=1)
        self.navigate(page,'learn');page.locator('[data-lesson="lesson-1"]').click();page.locator('[data-start-exercise="lesson-1"]').click();self.move(page,'e2e4',1);page.locator('#check-exercise').click()
        page.wait_for_function("document.querySelector('#coach-output').textContent.includes('Exercise completed')")
        self.check('Playable lesson completion records learning evidence',self.get(page,'/progress')['lessons_completed']>=1)
        self.navigate(page,'studies');page.locator('[data-start-exercise="opening-1"]').click();page.locator('#play-study-line').click();page.wait_for_function('document.querySelectorAll("#move-history [data-ply]").length>=5')
        self.check('Opening study line is replayed through server validation',len(self.current(page)['moves'])==5)
        self.navigate(page,'research');page.locator('[data-action="rank-position"]').click();page.wait_for_selector('#relevance-ranking tbody tr')
        self.check('Relevance dashboard displays actual candidate rankings',page.locator('#relevance-ranking tbody tr').count()>0)
        self.screenshot(page,'standalone-relevance-dashboard')
        page.close()
    def responsive(self,context,browser):
        mobile=browser.new_context(storage_state=context.storage_state(),viewport={'width':390,'height':844},is_mobile=True,has_touch=True,accept_downloads=True)
        page=self.watch(mobile.new_page());page.goto(self.args.backend,wait_until='networkidle');page.wait_for_selector('#chessboard .square')
        self.new_game(page,'human')
        for sq in ('e2','e4'):
            loc=page.locator(f'[data-square="{sq}"]');loc.scroll_into_view_if_needed();box=loc.bounding_box();page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
        page.wait_for_function('document.querySelectorAll("#move-history [data-ply]").length===1')
        self.check('Mobile touch makes an accepted legal move',self.current(page)['moves'][0]['uci']=='e2e4')
        size=page.evaluate('({overflow:document.documentElement.scrollWidth-innerWidth,width:innerWidth})');box=page.locator('#chessboard').bounding_box()
        self.check('390px responsive board has no horizontal overflow',size['overflow']<=1 and box['x']>=0 and box['x']+box['width']<=size['width']+1,viewport=size['width'],board_width=box['width'])
        self.screenshot(page,'mobile-touch-board');mobile.close()
    def admin_login(self,page):
        page.goto(self.args.joomla+'/administrator/index.php',wait_until='networkidle')
        if page.locator('#mod-login-username').count():
            page.locator('#mod-login-username').fill(self.access['admin_username']);page.locator('#mod-login-password').fill(self.access['admin_password']);page.locator('button[type=submit]').click();page.wait_for_load_state('networkidle')
        if page.get_by_text('Hide Forever',exact=True).count():page.get_by_text('Hide Forever',exact=True).click();page.wait_for_timeout(400)
        self.check('Independent Joomla administrator authenticated',page.locator('#mod-login-username').count()==0)
    def joomla(self,context):
        page=self.watch(context.new_page());self.admin_login(page)
        page.goto(self.args.joomla+'/administrator/index.php?option=com_installer&view=install',wait_until='networkidle')
        page.wait_for_selector('input[type=file]',state='attached')
        self.check('Actual Joomla extension installer exposed upload input',page.locator('input[type=file]').count()>0)
        self.package_tested_sha256=hashlib.sha256(Path(self.args.package).read_bytes()).hexdigest()
        page.locator('input[type=file]').first.set_input_files(self.args.package)
        deadline=time.monotonic()+75;message=''
        while time.monotonic()<deadline:
            message=page.locator('#system-message-container').inner_text() if page.locator('#system-message-container').count() else ''
            if re.search(r'(installation|installing).*(successful|success)|successfully',message,re.I):break
            candidates=page.get_by_role('button',name=re.compile('Upload.*Install',re.I))
            if candidates.count() and candidates.first.is_visible() and candidates.first.is_enabled():candidates.first.click()
            page.wait_for_timeout(500)
        self.check('Joomla ZIP genuinely installed through administrator browser',bool(re.search(r'(installation|installing).*(successful|success)|successfully',message,re.I)),message=self.redact(message))
        self.check('Joomla installer reports no missing files or installation warnings',not re.search(r'\bWarning\b|File does not exist|JInstaller:',message,re.I))
        self.screenshot(page,'joomla-administrator-package-installed')
        page.goto(self.args.joomla+'/administrator/index.php?option=com_chesselo5000',wait_until='networkidle')
        page.wait_for_function("document.querySelector('#ch-status')?.textContent.includes('Connected')")
        self.check('Native Joomla administrator connects to chess backend','Connected' in page.locator('#ch-status').inner_text())
        form=page.locator('form[data-collection="lessons"]');identity='browser-qa-'+self.stamp.lower()
        form.locator('[name=id]').fill(identity);form.locator('[name=title]').fill('Browser acceptance exercise');form.locator('[name=fen]').fill(START);form.locator('[name=body]').fill('Develop the e-pawn by playing e4.');form.locator('[name=moves]').fill('e2e4');form.locator('button[type=submit]').click()
        page.wait_for_function("document.querySelector('form[data-collection=lessons] .message').textContent.includes('Revision saved')")
        self.check('Joomla administrator saves a rules-validated content revision',True,content_id=identity)
        self.screenshot(page,'joomla-native-administration')
        page.goto(self.args.joomla+'/index.php?option=com_users&view=login',wait_until='networkidle')
        username=page.locator('input[name=username]')
        if username.count():
            username.first.fill(self.access['admin_username']);page.locator('input[name=password]').first.fill(self.access['admin_password']);page.locator('form').filter(has=page.locator('input[name=username]')).locator('button[type=submit]').click();page.wait_for_load_state('networkidle')
        page.goto(self.args.joomla+'/index.php?option=com_chesselo5000',wait_until='networkidle');page.wait_for_selector('#chessboard .square')
        page.wait_for_function("document.querySelector('#account-button').textContent!=='Sign in'")
        self.check('Joomla frontend authenticates using supported session bridge',page.locator('#chessboard .square').count()==64)
        self.new_game(page,'engine');self.move(page,'e2e4',2)
        game=self.current(page);self.legal_replay(game)
        self.check('Joomla frontend plays human move and actual legal engine reply',len(game['moves'])==2 and game['moves'][0]['uci']=='e2e4')
        self.checkpoint['joomla_game']={k:game[k] for k in ('id','fen','moves','version','status','turn')}
        self.screenshot(page,'joomla-playable-engine-board')
        self.navigate(page,'analysis');page.locator('#analysis-time').select_option('500');page.locator('#analyze-position').click();page.wait_for_function("['ANALYSIS COMPLETE','CACHED RESULT'].includes(document.querySelector('#engine-state').textContent)",timeout=30000)
        self.check('Joomla frontend displays actual engine analysis through authenticated bridge',page.locator('.analysis-line').count()>=1)
        self.screenshot(page,'joomla-engine-analysis')
        page.close()
    def after_restart(self,context):
        checkpoint=json.loads((ROOT/'evidence/browser/restart-checkpoint.json').read_text(encoding='utf-8'))
        page=self.watch(context.new_page());page.goto(self.args.backend,wait_until='networkidle');page.wait_for_selector('#chessboard .square')
        if page.locator('#account-button').inner_text()=='Sign in':self.signin_standalone(page)
        for key in ('resumable_game','terminal_game','imported_study'):
            expected=checkpoint[key];actual=self.get(page,'/games/'+expected['id']);self.legal_replay(actual)
            self.check('Backend restart preserves '+key,all(actual[k]==expected[k] for k in ('fen','moves','status')) and actual['version']==expected['version'])
            if key=='terminal_game':self.check('Checkmated game does not resume active after restart',actual['status']=='finished' and actual['result']=='0-1')
        self.navigate(page,'archive');identity=checkpoint['resumable_game']['id'];page.locator(f'[data-open-game="{identity}"]').click();page.wait_for_function('(id)=>localStorage.getItem("chesselo5000.game")===id',arg=identity)
        before=self.current(page);self.move(page,'f1c4',len(before['moves'])+2);after=self.current(page);self.legal_replay(after)
        self.check('Browser reopens exact saved game and continues against engine after restart',after['moves'][:len(before['moves'])]==before['moves'] and len(after['moves'])==len(before['moves'])+2)
        self.screenshot(page,'standalone-after-restart-continued');page.close()
        if checkpoint.get('joomla_game'):
            page=self.watch(context.new_page());page.goto(self.args.joomla+'/index.php?option=com_chesselo5000',wait_until='networkidle');page.wait_for_selector('#chessboard .square');page.wait_for_function("document.querySelector('#account-button').textContent!=='Sign in'")
            expected=checkpoint['joomla_game'];actual=self.get(page,'/games/'+expected['id']);self.legal_replay(actual)
            self.check('Joomla bridge reopens exact persisted game after backend restart',actual['fen']==expected['fen'] and actual['moves']==expected['moves'] and actual['version']==expected['version'])
            self.screenshot(page,'joomla-after-backend-restart');page.close()
    def run(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=self.args.edge,headless=True)
            state_path=self.private/'browser-acceptance-state.json'
            settings=dict(viewport={'width':1440,'height':1000},accept_downloads=True)
            if self.args.phase=='after-restart' and state_path.is_file():settings['storage_state']=str(state_path)
            context=browser.new_context(**settings)
            self.browser_version=browser.version
            if self.args.phase=='before-restart':
                self.scenario('standalone_scenario',lambda:self.standalone(context))
                self.scenario('mobile_scenario',lambda:self.responsive(context,browser))
                self.scenario('joomla_scenario',lambda:self.joomla(context))
                if self.checkpoint:(ROOT/'evidence/browser/restart-checkpoint.json').write_text(json.dumps(self.checkpoint,indent=2),encoding='utf-8')
                context.storage_state(path=str(state_path))
            elif self.args.phase=='joomla-install':
                self.scenario('joomla_scenario',lambda:self.joomla(context))
                context.storage_state(path=str(state_path))
            else:self.scenario('restart_scenario',lambda:self.after_restart(context))
            context.close();browser.close()
        self.check('No uncaught browser JavaScript errors',not self.errors,errors=self.errors)
    def report(self):
        result=dict(schema_version='chesselo5000.browser-acceptance/1',phase=self.args.phase,started_utc=self.stamp,finished_utc=datetime.now(timezone.utc).isoformat(),browser=getattr(self,'browser_version',None),browser_executable=self.args.edge,backend_url=self.args.backend,joomla_url=self.args.joomla,package_tested_sha256=self.package_tested_sha256,package_current_sha256=hashlib.sha256(Path(self.args.package).read_bytes()).hexdigest(),status='PASS' if self.cases and all(c['status']=='PASS' for c in self.cases) else 'FAIL',counts={'passed':sum(c['status']=='PASS' for c in self.cases),'failed':sum(c['status']=='FAIL' for c in self.cases)},cases=self.cases,evidence_directory=str(self.out),scope='Real installed Microsoft Edge in isolated headless browser contexts; no user browser profile used; UI actions verified against persisted server state.')
        text=json.dumps(result,indent=2,ensure_ascii=False)
        for path in (self.out/'verification.json',ROOT/'evidence/browser'/f'{self.args.phase}-latest.json'):path.write_text(text,encoding='utf-8')
        print(json.dumps({k:result[k] for k in ('phase','status','counts','evidence_directory')}))
        return result['status']=='PASS'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('before-restart','after-restart','joomla-install'),default='before-restart')
    parser.add_argument('--backend',default='http://127.0.0.1:18961')
    parser.add_argument('--joomla',default='http://127.0.0.1:18952')
    parser.add_argument('--package',default=str(ROOT/'dist/CHESS-ELO-5000-Joomla-Package.zip'))
    parser.add_argument('--edge',default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args=parser.parse_args();h=Acceptance(args)
    try:h.run()
    except Exception as exc:h.cases.append(dict(name='harness_completion',status='FAIL',error=h.redact(f'{type(exc).__name__}: {exc}')))
    sys.exit(0 if h.report() else 1)

if __name__=='__main__':main()
