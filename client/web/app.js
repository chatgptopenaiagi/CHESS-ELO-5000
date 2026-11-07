/* CHESS ELO 5000 — buildless client. Chess rules and durable state belong to the server. */
(() => {
  'use strict';
  const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const SYMBOLS = {K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'};
  const NAMES = {k:'king',q:'queen',r:'rook',b:'bishop',n:'knight',p:'pawn'};
  function escapeHTML(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function parseFen(fen) {
    const parts = String(fen).trim().split(/\s+/);
    const rows = (parts[0] || '').split('/');
    if (rows.length !== 8 || !['w','b'].includes(parts[1])) throw new Error('The server returned an invalid board position.');
    const board = {};
    rows.forEach((row, index) => {
      let file = 0;
      for (const ch of row) {
        if (/^[1-8]$/.test(ch)) file += Number(ch);
        else if (Object.hasOwn(SYMBOLS, ch) && file < 8) { board[String.fromCharCode(97 + file) + (8 - index)] = ch; file++; }
        else throw new Error('The server returned an invalid board position.');
      }
      if (file !== 8) throw new Error('The server returned an invalid board position.');
    });
    return board;
  }
  function apiURL(config, resource) {
    if (!resource.startsWith('/')) throw new Error('API resources must use an absolute resource path.');
    const base = config.apiBase || '/api/v1';
    if (config.proxy) return base + encodeURIComponent('/api/v1' + resource);
    return base.replace(/\/$/,'') + resource;
  }
  function formatClock(ms) {
    if (ms === null || ms === undefined || !Number.isFinite(Number(ms))) return '—:—';
    const seconds = Math.max(0, Math.ceil(Number(ms) / 1000));
    return Math.floor(seconds / 60).toString().padStart(2,'0') + ':' + (seconds % 60).toString().padStart(2,'0');
  }
  function boardCoordinates(rotated) {
    const files = rotated ? 'hgfedcba' : 'abcdefgh';
    const ranks = rotated ? [1,2,3,4,5,6,7,8] : [8,7,6,5,4,3,2,1];
    return ranks.flatMap(rank => [...files].map(file => file + rank));
  }
  const utils = {parseFen,apiURL,formatClock,boardCoordinates,escapeHTML,START_FEN};
  if (typeof document === 'undefined') { if (typeof module !== 'undefined') module.exports = utils; return; }
  window.ChessUI = utils;
  const $ = selector => document.querySelector(selector);
  const config = window.CHESS_CONFIG || {};
  const state = {view:config.defaultView || 'play',game:null,replay:null,selected:null,rotated:false,busy:false,engineBusy:false,analysis:null,analysisFen:null,analysisJob:null,analysisTimer:null,csrf:config.csrfToken || null,user:null,engines:[],sessionChecked:false,gameReceivedAt:Date.now(),exercise:null,contentRecords:[],pointer:null,textAction:null,researchTimer:null,tournamentTimer:null,clockRefresh:false};
  const headings = {
    play:['YOUR NEXT MOVE STARTS HERE','A beautiful game.<br><em>A deeper understanding.</em>','Play with purpose. Explore every possibility. Make the next move yours.','Play chess'],
    analysis:['FOLLOW THE POSITION','Every move has a reason.<br><em>Find yours.</em>','Explore real engine evaluations, validated variations, and the ideas behind a position.','Analysis board'],
    archive:['YOUR CHESS, REMEMBERED','Every game.<br><em>Every possibility.</em>','Replay saved games, revisit a turning point, or start a separate study from PGN.','Game archive'],
    learn:['BUILD YOUR UNDERSTANDING','Small discoveries.<br><em>Lasting improvement.</em>','Playable lessons, thoughtful practice, and progress grounded in completed exercises.','Learn & practice'],
    puzzles:['SEE THE OPPORTUNITY','Find the move.<br><em>Understand the idea.</em>','Solve legal, verified tactical exercises. Take a hint, test a line, and try again.','Tactical puzzles'],
    studies:['PATTERNS WORTH KNOWING','A strong beginning.<br><em>A precise finish.</em>','Study opening ideas and endgame technique on a board you can explore.','Opening & endgames'],
    research:['WHAT DESERVES ATTENTION?','Calculate with purpose.<br><em>Measure the difference.</em>','Compare conventional search with transparent and learned relevance under recorded budgets.','Relevance lab'],
    tournaments:['THE LOCAL ENGINE ARENA','Let the games<br><em>tell the story.</em>','Reproducible engine play, paired positions, measured outcomes, and honest uncertainty.','Tournaments']
  };
  function toast(message, error=false) {
    const node = document.createElement('div'); node.className = 'toast' + (error ? ' error' : ''); node.textContent = message;
    $('#toasts').append(node); setTimeout(() => node.remove(), error ? 8000 : 4500);
  }
  function openDialog(id) { const d = $('#' + id); if (!d.open) d.showModal(); }
  function closeDialog(id) { $('#' + id).close(); }
  async function api(resource, options={}) {
    const method = options.method || 'GET';
    let url = apiURL(config,resource);
    const headers = {'Accept':'application/json',...(options.headers || {})};
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET' && method !== 'HEAD') {
      if (config.joomla && config.csrfParam) url += (url.includes('?') ? '&' : '?') + encodeURIComponent(config.csrfParam) + '=1';
      else if (state.csrf) headers['X-CSRF-Token'] = state.csrf;
    }
    const response = await fetch(url,{method,headers,credentials:'same-origin',body:options.body === undefined ? undefined : JSON.stringify(options.body),signal:options.signal});
    const contentType = response.headers.get('content-type') || '';
    const result = options.text ? await response.text() : contentType.includes('json') ? await response.json() : {message:await response.text()};
    if (!response.ok) {
      if (response.status === 401 && !options.quietAuth) showLogin(result.login_url);
      const error = new Error(typeof result === 'string' ? result : result.message || result.error || `Request failed (${response.status}).`);
      error.status = response.status; error.details = result; throw error;
    }
    return result;
  }
  function showLogin(url) {
    if (config.joomla) {
      $('#password-label').hidden = true;
      $('#owner-password').required = false;
      $('#login-form button[type=submit]').hidden = true;
      $('#login-description').textContent = 'Use your independent chess website account to save games and run analysis.';
      const link = $('#joomla-login-link'); link.href = url || config.loginUrl || 'index.php?option=com_users&view=login'; link.hidden = false;
    }
    openDialog('login-dialog');
  }
  async function requireSession() { if (state.user) return true; showLogin(); return false; }
  function setUser(user,csrf) {
    state.user = user; if (csrf) state.csrf = csrf;
    $('#account-button').textContent = typeof user === 'string' ? user : user?.name || user?.username || 'Owner';
  }
  async function startSession() {
    try { const s = await api('/session',{quietAuth:true}); setUser(s.user,s.csrf_token); }
    catch (e) { if (e.status !== 401) toast('The chess service could not be reached. Start the backend, then refresh.',true); }
    state.sessionChecked = true;
  }
  function gameId(game) { return game?.id || game?.game_id; }
  function normalizeGame(data) {
    const game = data.game || data;
    if (!game.fen || !gameId(game)) throw new Error('The game response is missing its saved identity or position.');
    parseFen(game.fen);
    game.moves = game.moves || [];
    game.legal_moves = game.legal_moves || [];
    return game;
  }
  function setGame(data,resetReplay=true) {
    state.game = normalizeGame(data); state.selected = null; state.gameReceivedAt = Date.now(); state.clockRefresh = false;
    if (resetReplay) state.replay = null;
    try { localStorage.setItem('chesselo5000.game',gameId(state.game)); } catch {}
    renderBoard(); renderGame(); updateActions();
  }
  function displayedFen() {
    if (!state.game) return START_FEN;
    if (state.replay === null) return state.game.fen;
    return state.replay === 0 ? state.game.starting_fen || START_FEN : state.game.moves[state.replay-1]?.fen || state.game.fen;
  }
  function displayedPly() { return state.replay === null ? state.game?.moves.length || 0 : state.replay; }
  function renderBoard() {
    const fen = displayedFen(); const pieces = parseFen(fen); const coords = boardCoordinates(state.rotated); const displayedTurn = fen.split(' ')[1];
    const game = state.game; const live = state.replay === null; const moves = game?.moves || [];
    const last = live ? game?.last_move || moves.at(-1)?.uci : state.replay ? moves[state.replay-1]?.uci : null;
    const legal = live && state.selected ? game?.legal_moves.filter(m => m.startsWith(state.selected)).map(m => m.slice(2,4)) || [] : [];
    const inCheck = live && game?.check;
    const focusSquare = document.activeElement?.dataset?.square;
    $('#chessboard').innerHTML = coords.map((sq,index) => {
      const piece = pieces[sq]; const light = ((sq.charCodeAt(0)-97)+Number(sq[1])) % 2 === 0;
      const classes = ['square',!light?'dark':'',piece?'has-piece':'',sq===state.selected?'selected':'',last && (sq===last.slice(0,2)||sq===last.slice(2,4))?'last-move':'',legal.includes(sq)?'legal':'',inCheck && piece===(displayedTurn==='w'?'K':'k')?'in-check':''].filter(Boolean).join(' ');
      const label = sq + (piece ? ', ' + (piece===piece.toUpperCase()?'white ':'black ') + NAMES[piece.toLowerCase()] : ', empty');
      return `<button type="button" class="${classes}" role="gridcell" data-square="${sq}" aria-label="${label}" aria-selected="${sq===state.selected}" tabindex="${sq===(focusSquare || 'e2')?0:-1}">${piece?`<span class="piece ${piece===piece.toUpperCase()?'white':'black'}" aria-hidden="true">${SYMBOLS[piece]}</span>`:''}${index%8===0?`<span class="coordinate rank">${sq[1]}</span>`:''}${index>=56?`<span class="coordinate file">${sq[0]}</span>`:''}</button>`;
    }).join('');
    $('#chessboard').setAttribute('aria-label',`Chessboard, ${state.rotated?'black':'white'} at bottom${game?', '+(live?'current position':'replay position '+state.replay):', new game preview'}`);
    if (focusSquare) $('#chessboard [data-square="'+focusSquare+'"]').focus({preventScroll:true});
    $('#replay-label').textContent = state.replay===null ? 'LIVE BOARD' : `PLY ${state.replay} / ${moves.length}`;
    if (state.analysisFen !== fen) { $('#evaluation-fill').style.height = '50%'; $('#evaluation-rail').setAttribute('aria-label','No engine evaluation for this position'); }
    if (state.analysis) renderAnalysis();
  }
  function playerName(color) {
    const game = state.game; if (!game) return color==='white'?'White pieces':'Black pieces';
    if (game.mode==='engine') return game.human_color===color ? 'You' : game.engine_name || state.engines.find(e=>e.available)?.name || 'Local UCI engine';
    return game[color+'_name'] || game.players?.[color] || game[color] || (color==='white'?'White':'Black');
  }
  function renderGame() {
    const game = state.game; const top = state.rotated?'white':'black'; const bottom = state.rotated?'black':'white';
    $('#top-player').textContent = playerName(top); $('#bottom-player').textContent = playerName(bottom);
    const detail = color => !game ? (color==='white'?'Choose a game to begin':'New game preview') : game.mode==='study'?'Study board':game.mode==='engine'?(game.human_color===color?'Human player':'Local engine · bounded thinking'):'Human player';
    $('#top-player-detail').textContent = detail(top); $('#bottom-player-detail').textContent = detail(bottom);
    $('#game-card-title').textContent = game ? game.status==='finished'?'A game to remember.':state.exercise?state.exercise.title:'Your game, in progress.' : 'The game is yours.';
    $('#game-mode-label').textContent = !game?'READY WHEN YOU ARE':game.mode==='engine'?'HUMAN VS ENGINE':game.mode==='study'?'STUDY BOARD':'LOCAL TWO PLAYER';
    $('#game-summary').textContent = !game?'A local engine. Authoritative chess rules. Every accepted move saved.':state.exercise?state.exercise.objective:game.status==='finished'?formatReason(game.reason):'Every accepted move is validated and saved to your independent archive.';
    $('#side-to-move').textContent = game ? game.status==='finished'?'Finished':game.turn==='white'?'White':'Black' : 'White';
    $('#game-result').textContent = game?.result==='*'?'In play':game?.result || '—';
    $('#move-count').textContent = String(Math.floor((game?.moves.length || 0)/2)+1).padStart(2,'0');
    const captures = game?.captures;
    $('#captured-pieces').textContent = captures ? [...(captures.white || []),...(captures.black || [])].map(p=>SYMBOLS[p] || '').join('') || '—' : '—';
    const moves = game?.moves || [];
    if (moves.length) {
      const rows = []; for(let i=0;i<moves.length;i+=2) rows.push(`<div class="move-row"><span class="move-number">${Math.floor(i/2)+1}.</span>${[i,i+1].map(j=>moves[j]?`<button type="button" data-ply="${j+1}" class="${displayedPly()===j+1?'current':''}">${escapeHTML(moves[j].san || moves[j].uci)}</button>`:'<span></span>').join('')}</div>`);
      $('#move-history').innerHTML = rows.join('');
      if (state.replay===null) $('#move-history').scrollTop = $('#move-history').scrollHeight;
    } else $('#move-history').innerHTML = '<div class="empty-state"><span>♙</span><p>Every great game begins<br>with a single move.</p></div>';
    let status = !game?'Start a new game or open a position from your archive.':state.replay!==null?'Viewing a saved position. Return to the current position to continue playing.':game.status==='finished'?formatReason(game.reason):state.engineBusy?'The local engine is thinking…':game.check?`${capitalize(game.turn)} is in check.`:`${capitalize(game.turn)} to move. Select a piece to see legal moves.`;
    if (state.exercise && game && game.status!=='finished') status = state.exercise.objective + ' · Play your line, then check the exercise.';
    $('#board-status').textContent = status;
    renderClocks(); renderExerciseAction();
  }
  function capitalize(text) { return String(text || '').replace(/^./,c=>c.toUpperCase()); }
  function formatReason(reason) { return capitalize(String(reason || 'Game finished').replace(/_/g,' ')) + '.'; }
  function renderClocks() {
    const game=state.game,top=state.rotated?'white':'black',bottom=state.rotated?'black':'white';
    const remaining = color => {
      const value=game?.[color+'_ms']; if (value===null||value===undefined||game?.mode==='study'||game?.time_seconds===0) return null;
      return value - (game.status==='active'&&game.turn===color ? Date.now()-state.gameReceivedAt : 0);
    };
    $('#top-clock').textContent=formatClock(remaining(top)); $('#bottom-clock').textContent=formatClock(remaining(bottom));
    $('#top-clock').classList.toggle('active',!!game&&game.status==='active'&&game.turn===top);
    $('#bottom-clock').classList.toggle('active',!!game&&game.status==='active'&&game.turn===bottom);
    if(game&&game.status==='active'&&game.mode!=='study'&&remaining(game.turn)!==null&&remaining(game.turn)<=0&&!state.clockRefresh&&!state.busy){
      state.clockRefresh=true;
      api('/games/'+encodeURIComponent(gameId(game))+'/tick',{method:'POST',quietAuth:true,body:{expected_version:game.version,request_id:crypto.randomUUID()}}).then(g=>setGame(g,false)).catch(async error=>{if(error.status===409)await refreshCurrentGame();else toast(error.message,true);});
    }
  }
  function updateActions() {
    const g=state.game,active=g?.status==='active',live=state.replay===null;
    $('#engine-reply').disabled=!g||!active||g.mode!=='engine'||g.turn===g.human_color||state.busy||state.engineBusy||!live;
    $('#engine-reply').textContent=state.engineBusy?'Thinking…':'Engine reply';
    $('#resign-game').disabled=!g||!active||g.mode==='study'||state.busy;
    $('#draw-game').disabled=!g||!active||g.mode==='study'||state.busy;
    $('#undo-move').disabled=!g||g.mode!=='study'||!g.moves.length||state.busy;
    $('#restart-game').disabled=!g||state.busy||state.engineBusy;
    $('#analyze-position').disabled=state.busy||!!state.analysisJob;
    $('#cancel-analysis').hidden=!state.analysisJob;
    $('#branch-position').disabled=!g||state.busy;
    document.querySelectorAll('[data-replay]').forEach(button=>button.disabled=!g||!g.moves.length);
  }
  async function chooseSquare(square) {
    const game=state.game;
    if(!game){openDialog('new-game-dialog');return;}
    if(state.busy||state.engineBusy||state.replay!==null||game.status==='finished')return;
    if(game.mode==='engine'&&game.turn!==game.human_color){toast('It is the engine’s turn. Choose Engine reply to continue.');return;}
    if(state.selected===square){state.selected=null;renderBoard();return;}
    const candidates=state.selected?game.legal_moves.filter(m=>m.startsWith(state.selected+square)):[];
    if(candidates.length){
      if(candidates.some(m=>m.length===5)) { choosePromotion(candidates); return; }
      await submitMove(candidates[0]); return;
    }
    state.selected=game.legal_moves.some(m=>m.startsWith(square))?square:null;
    renderBoard();
  }
  function choosePromotion(candidates) {
    $('#promotion-options').innerHTML=candidates.map(m=>`<button type="button" data-promotion="${m}" aria-label="Promote to ${NAMES[m[4]]}">${SYMBOLS[state.game.turn==='white'?m[4].toUpperCase():m[4]]}</button>`).join('');
    openDialog('promotion-dialog');
  }
  async function submitMove(uci) {
    if(state.busy)return; state.busy=true;updateActions();
    try {
      const game=await api('/games/'+encodeURIComponent(gameId(state.game))+'/moves',{method:'POST',body:{uci,expected_version:state.game.version,request_id:crypto.randomUUID()}});
      setGame(game);
      if(state.exercise&&state.game.status==='finished')toast('The position has ended. Check your exercise to record the result.');
    } catch(e) { toast(e.message,true);if(e.status===409)await refreshCurrentGame(); }
    finally {state.busy=false;updateActions();}
    if(state.game?.mode==='engine'&&state.game.status==='active'&&state.game.turn!==state.game.human_color)await requestEngineReply();
  }
  async function refreshCurrentGame() {if(state.game){try{setGame(await api('/games/'+encodeURIComponent(gameId(state.game))));}catch(e){toast(e.message,true);}}}
  async function requestEngineReply() {
    const g=state.game;if(!g||state.engineBusy||state.busy||g.status!=='active'||g.mode!=='engine'||g.turn===g.human_color)return;
    state.engineBusy=true;renderGame();updateActions();
    try{setGame(await api('/games/'+encodeURIComponent(gameId(g))+'/engine',{method:'POST',body:{expected_version:g.version,request_id:crypto.randomUUID(),movetime_ms:Number($('#engine-time').value)}}));}
    catch(e){toast(e.message,true);if(e.status===409)await refreshCurrentGame();}
    finally{state.engineBusy=false;renderGame();updateActions();}
  }
  async function newGame(event) {
    event.preventDefault();if(!await requireSession()||state.busy)return;
    let created=false;state.busy=true;updateActions();
    try{
      const body={mode:$('#new-mode').value,human_color:$('#new-color').value,time_seconds:Number($('#new-time').value),increment_seconds:Number($('#new-increment').value)};
      if($('#new-fen').value.trim())body.fen=$('#new-fen').value.trim();
      const skill=$('#new-skill');if(skill)body.skill_level=Number(skill.value);
      const engine=$('#new-engine');if(engine?.value)body.engine_id=engine.value;
      state.exercise=null;setGame(await api('/games',{method:'POST',body}));created=true;state.rotated=body.mode==='engine'&&body.human_color==='black';renderBoard();renderGame();closeDialog('new-game-dialog');await navigate(body.mode==='study'?'analysis':'play');toast('Your new game is ready.');
    }catch(e){toast(e.message,true);}
    finally{state.busy=false;updateActions();}
    if(created&&state.game?.mode==='engine'&&state.game.status==='active'&&state.game.turn!==state.game.human_color)await requestEngineReply();
  }
  async function gameAction(action,extra={}) {
    if(!state.game||state.busy)return;
    if(action==='resign'&&!confirm('Resign this local game? The completed result will be saved.'))return;
    state.busy=true;updateActions();
    try{setGame(await api('/games/'+encodeURIComponent(gameId(state.game))+'/'+action,{method:'POST',body:{expected_version:state.game.version,request_id:crypto.randomUUID(),...extra}}));toast(action==='undo'?'The study move was undone.':'Game state saved.');}
    catch(e){toast(e.message,true);if(e.status===409)await refreshCurrentGame();}
    finally{state.busy=false;updateActions();}
  }
  async function restartGame(){
    const previous=state.game;if(!previous||state.busy||state.engineBusy||!await requireSession())return;
    if(!confirm('Start again from this game’s initial position? The existing game will remain in your archive.'))return;
    state.busy=true;updateActions();let created=false;
    try{setGame(await api('/games',{method:'POST',body:{mode:previous.mode,human_color:previous.human_color,time_seconds:previous.time_seconds,increment_seconds:previous.increment_seconds,skill_level:previous.skill_level,fen:previous.starting_fen,white:previous.white,black:previous.black}}));created=true;toast('A new game has started. Your previous game is preserved.');}
    catch(e){toast(e.message,true);}finally{state.busy=false;updateActions();}
    if(created&&state.game.mode==='engine'&&state.game.status==='active'&&state.game.turn!==state.game.human_color)await requestEngineReply();
  }
  function replay(action) {
    if(!state.game)return;const count=state.game.moves.length,at=displayedPly();
    if(action==='first')state.replay=0;else if(action==='last')state.replay=null;else if(action==='previous')state.replay=Math.max(0,at-1);else if(action==='next')state.replay=at+1>=count?null:at+1;else state.replay=Number(action)>=count?null:Number(action);
    state.selected=null;renderBoard();renderGame();updateActions();
  }
  async function runAnalysis() {
    if(!await requireSession()||state.analysisJob)return;
    const fen=displayedFen();state.analysisFen=fen;state.analysis=null;$('#engine-state').textContent='QUEUED';$('#engine-state').className='pill running';$('#analysis-results').innerHTML='<p class="muted"><span class="busy-dot"></span>Requesting a bounded local engine analysis…</p>';
    try{const job=await api('/analysis',{method:'POST',body:{fen,movetime_ms:Number($('#analysis-time').value),multipv:3}});state.analysisReuse=job.cache_hit||job.duplicate||false;state.analysisJob=job.id||job.job_id;updateActions();await pollAnalysis();}
    catch(e){state.analysisJob=null;$('#engine-state').textContent='FAILED';$('#engine-state').className='pill';$('#analysis-results').innerHTML=`<p class="error-text">${escapeHTML(e.message)}</p>`;toast(e.message,true);updateActions();}
  }
  async function pollAnalysis() {
    if(!state.analysisJob)return;const requestedId=state.analysisJob;
    try{
      const job=await api('/analysis/'+encodeURIComponent(requestedId));
      if(state.analysisJob!==requestedId)return;
      const status=String(job.status||'').toLowerCase();
      if(['completed','succeeded','complete'].includes(status)){state.analysis={...(job.result||job),id:requestedId,cached:state.analysisReuse||job.cache_hit||job.cached||job.result?.cached||false};state.analysisJob=null;renderAnalysis();updateActions();}
      else if(['failed','cancelled','canceled','interrupted'].includes(status)){throw new Error(job.error?.message||job.error||job.message||'Analysis did not complete.');}
      else{ $('#engine-state').textContent=status.toUpperCase()||'RUNNING';state.analysisTimer=setTimeout(pollAnalysis,450); }
    }catch(e){if(state.analysisJob!==requestedId)return;state.analysisJob=null;$('#engine-state').textContent='FAILED';$('#engine-state').className='pill';$('#analysis-results').innerHTML=`<p class="error-text">${escapeHTML(e.message)}</p>`;updateActions();}
  }
  async function cancelAnalysis(){const id=state.analysisJob;if(!id)return;try{await api('/analysis/'+encodeURIComponent(id)+'/cancel',{method:'POST',body:{}});if(state.analysisJob===id){state.analysisJob=null;clearTimeout(state.analysisTimer);$('#engine-state').textContent='CANCELLED';$('#engine-state').className='pill';$('#analysis-results').innerHTML='<p class="muted">Analysis cancelled. No completed result is claimed.</p>';updateActions();}}catch(e){toast(e.message,true);}}
  function renderAnalysis() {
    const analysis=state.analysis;if(!analysis)return;
    const current=state.analysisFen===displayedFen();
    $('#engine-state').textContent=!current?'PREVIOUS POSITION':analysis.cached?'CACHED RESULT':'ANALYSIS COMPLETE';$('#engine-state').className=current?'pill success':'pill';
    const lines=analysis.lines||analysis.evaluations||[];
    $('#analysis-results').innerHTML=lines.length?lines.map((line,index)=>{
      const score=line.score||{};const value=Number(score.value);const scoreText=score.type==='mate'?(value>=0?'+':'−')+'M'+Math.abs(value):score.type==='cp'?(value>=0?'+':'')+(value/100).toFixed(2):'—';
      const pv=line.san?.join(' ')||line.pv?.join(' ')||'No principal variation reported.';
      if(index===0&&state.analysisFen===displayedFen()&&Number.isFinite(value)){const percent=score.type==='mate'?(value>0?97:3):50+43*Math.tanh(value/450);$('#evaluation-fill').style.height=percent+'%';$('#evaluation-rail').setAttribute('aria-label','Engine evaluation '+scoreText+' from '+(score.perspective||'reported')+' perspective');}
      return `<div class="analysis-line"><div class="analysis-score">${escapeHTML(scoreText)}</div><div><div class="analysis-pv">${escapeHTML(pv)}</div><div class="analysis-meta">DEPTH ${escapeHTML(line.depth??'—')} · ${escapeHTML(formatNumber(line.nodes))} NODES · ${escapeHTML(score.perspective||'reported')} perspective</div></div></div>`;
    }).join(''):'<p class="muted">The engine completed without a principal variation.</p>';
    if(analysis.engine?.name)$('#analysis-results').insertAdjacentHTML('beforeend',`<p class="analysis-meta">${escapeHTML(analysis.engine.name)}${analysis.cached?' · reused matching engine and budget identity':''}</p>`);
    if(!current)$('#analysis-results').insertAdjacentHTML('afterbegin','<p class="muted">Saved analysis for a different position. Analyze the displayed board for a matching result.</p>');
  }
  function formatNumber(n){return Number.isFinite(Number(n))?Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1}).format(Number(n)):'—';}
  function savedDate(value){if(!value)return 'Saved locally';const date=new Date(typeof value==='number'?value*1000:value);return Number.isNaN(date.valueOf())?'Saved locally':date.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});}
  async function explainPosition(){
    if(!await requireSession())return;$('#coach-output').hidden=false;$('#coach-output').textContent='Reading the position…';
    try{const body={fen:displayedFen()};if(state.analysisFen===displayedFen()&&state.analysis?.id)body.analysis_id=state.analysis.id;const result=await api('/coach',{method:'POST',body});$('#coach-output').innerHTML=(result.facts||[]).map(f=>`<p><strong>${escapeHTML(f.kind?.replace(/_/g,' ')||'POSITION FACT')}</strong><br>${escapeHTML(f.text)}</p>`).join('')+`<p>${escapeHTML(result.recommendation||'')}</p><p class="analysis-meta">PROVIDER: ${escapeHTML(result.provider||'deterministic')}</p>`;}
    catch(e){$('#coach-output').textContent=e.message;}
  }
  function showTextDialog({title,label,value='',submit,help='',action,readonly=false}){
    $('#text-dialog-title').textContent=title;$('#text-dialog-label').firstChild.textContent=label;$('#text-dialog-value').value=value;$('#text-dialog-value').readOnly=readonly;$('#text-dialog-submit').textContent=submit||'Save';$('#text-dialog-submit').hidden=readonly;$('#text-dialog-help').textContent=help;state.textAction=action;openDialog('text-dialog');
  }
  async function copyFen(){const fen=displayedFen();try{await navigator.clipboard.writeText(fen);toast('FEN copied to your clipboard.');}catch{showTextDialog({title:'Current position',label:'FEN',value:fen,readonly:true,help:'Select and copy this FEN position.'});}}
  async function exportPGN(id){try{const text=await api('/games/'+encodeURIComponent(id||gameId(state.game))+'/pgn',{text:true});const blob=new Blob([text],{type:'application/x-chess-pgn;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='CHESS-ELO-5000-'+(id||gameId(state.game))+'.pgn';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),3000);toast('PGN exported.');}catch(e){toast(e.message,true);}}
  async function importPGN(){if(!await requireSession())return;showTextDialog({title:'A game worth revisiting.',label:'PGN',submit:'Import as a separate study',help:'The server validates the complete game. Your original games remain unchanged.',action:async value=>{state.exercise=null;setGame(await api('/studies/import',{method:'POST',body:{pgn:value}}));closeDialog('text-dialog');await navigate('analysis');toast('PGN imported into a separate study.');}});}
  async function createBranch(){
    if(!state.game||!await requireSession())return;
    showTextDialog({title:'Explore another possibility.',label:'Continuation in UCI notation',submit:'Save variation',help:'Enter a legal line such as g1f3 b8c6. It begins at the displayed position and preserves the original game.',action:async value=>{const moves=value.trim().split(/\s+/).filter(Boolean);if(!moves.length)throw new Error('Enter at least one move.');const result=await api('/games/'+encodeURIComponent(gameId(state.game))+'/variations',{method:'POST',body:{ply:displayedPly(),moves,name:'Study variation'}});closeDialog('text-dialog');toast('Variation saved separately: '+result.id);$('#coach-output').hidden=false;$('#coach-output').innerHTML=`<p><strong>SAVED HYPOTHETICAL VARIATION</strong><br>${escapeHTML(moves.join(' '))}</p><p class="analysis-meta">ID ${escapeHTML(result.id)} · Original game preserved.</p>`;}});
  }
  async function navigate(view){
    if(!headings[view])view='play';state.view=view;
    const h=headings[view];$('#page-eyebrow').textContent=h[0];$('#page-title').innerHTML=h[1];$('#page-description').textContent=h[2];$('#breadcrumb').textContent=h[3];
    document.querySelectorAll('#navigation [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
    const boardView=['play','analysis'].includes(view);$('#board-view').hidden=!boardView;$('#content-view').hidden=boardView;$('#play-footer').hidden=view!=='play';$('#new-game-button').textContent=view==='analysis'?'＋ New study':'＋ New game';
    $('.sidebar').classList.remove('open');
    if(location.hash!=='#'+view)history.replaceState(null,'','#'+view);
    if(boardView){if(view==='analysis')$('#new-mode').value='study';else if($('#new-mode').value==='study')$('#new-mode').value='engine';renderBoard();renderGame();return;}
    $('#content-view').innerHTML='<div class="status-note"><span class="busy-dot"></span>Opening your '+escapeHTML(h[3].toLowerCase())+'…</div>';
    try{await ({archive:loadArchive,learn:loadLessons,puzzles:loadPuzzles,studies:loadStudies,research:loadResearch,tournaments:loadTournaments}[view])();}
    catch(e){$('#content-view').innerHTML=`<div class="empty-panel"><h2>${e.status===401?'Your studio is private.':'This section could not be loaded.'}</h2><p>${escapeHTML(e.message)}</p><button class="secondary-button" data-retry="${view}">Try again</button></div>`;}
  }
  async function loadArchive(){
    const data=await api('/games');const games=data.games||[];
    $('#content-view').innerHTML=`<div class="content-toolbar"><p class="muted">${games.length} saved ${games.length===1?'game':'games'} · Accepted moves survive restart.</p><div class="content-actions"><button class="secondary-button" data-action="import-pgn">Import PGN</button><button class="secondary-button" data-action="export-current" ${state.game?'':'disabled'}>Export current game</button></div></div>`+(games.length?`<div class="card"><table class="content-table"><thead><tr><th>GAME</th><th>RESULT</th><th class="hide-mobile">MOVES</th><th></th></tr></thead><tbody>${games.map(g=>`<tr><td><strong>${escapeHTML(g.white_name||g.players?.white||g.white||'White')} — ${escapeHTML(g.black_name||g.players?.black||g.black||(g.mode==='engine'?'Local engine':'Black'))}</strong><small>${escapeHTML(g.mode||'Game')} · ${escapeHTML(savedDate(g.created_at||g.created_utc))}</small></td><td>${escapeHTML(g.result||'*')}<small>${escapeHTML(g.reason||g.status||'')}</small></td><td class="hide-mobile">${escapeHTML(g.moves?.length??g.move_count??'—')}</td><td><button class="text-button" data-open-game="${escapeHTML(g.id)}">Open →</button> <button class="text-button" data-export-game="${escapeHTML(g.id)}">PGN ↓</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty-panel"><h2>Your story starts with a game.</h2><p>Create your first game or import a PGN to begin your archive.</p></div>');
  }
  async function loadLessons(){
    const [data,progress]=await Promise.all([api('/lessons'),api('/progress')]);const lessons=data.lessons||[];state.contentRecords=lessons;
    const completed=Array.isArray(progress.lessons_completed)?progress.lessons_completed.length:progress.lessons_completed||0;
    $('#content-view').innerHTML=`<div class="stats-grid"><div class="card stat-card"><small>Lessons completed</small><strong>${escapeHTML(completed)}</strong><span>Verified exercise completions</span></div><div class="card stat-card"><small>Puzzles solved</small><strong>${escapeHTML(progress.puzzles_solved||0)}</strong><span>Practiced, not a rating</span></div><div class="card stat-card"><small>Puzzles attempted</small><strong>${escapeHTML(progress.puzzles_attempted||0)}</strong><span>Every attempt teaches something</span></div><div class="card stat-card"><small>Study sessions</small><strong>${escapeHTML(progress.study_sessions||0)}</strong><span>Your independent learning history</span></div></div><div class="status-note">${escapeHTML(typeof progress.recommendation==='string'?progress.recommendation:progress.recommendation?.text||'Choose a lesson and complete its playable exercise to record progress.')}</div><div class="tile-grid">${lessons.map((l,index)=>`<article class="card content-tile"><div class="kicker">${escapeHTML(l.level||'CHESS LESSON')}</div><span class="tile-symbol">${['♙','♘','♗','♜','♛','♚'][index%6]}</span><h3>${escapeHTML(l.title)}</h3><p>${escapeHTML(l.objective||String(l.body||'').slice(0,120))}</p><button class="text-button" data-lesson="${escapeHTML(l.id)}">Open lesson <span>→</span></button></article>`).join('')}</div>`;
  }
  function showLesson(id){const l=state.contentRecords.find(r=>r.id===id);if(!l)return;$('#content-view').innerHTML=`<article class="card study-detail"><div class="kicker">${escapeHTML(l.level)}</div><h2>${escapeHTML(l.title)}</h2><p>${escapeHTML(l.body).replace(/\n/g,'<br>')}</p><div class="status-note">${escapeHTML(l.objective)}</div><button class="primary-button" data-start-exercise="${escapeHTML(l.id)}" data-kind="lesson">Practice on the board <span>→</span></button></article><button class="text-button" data-retry="learn">← All lessons</button>`;}
  async function loadPuzzles(){const data=await api('/puzzles');const puzzles=data.puzzles||[];state.contentRecords=puzzles;$('#content-view').innerHTML=`<div class="status-note">Play your answer on a study board, then check it against the verified objective. Hints and attempts are recorded separately.</div><div class="tile-grid">${puzzles.map(p=>`<article class="card content-tile"><div class="kicker">${escapeHTML(p.category?.replace(/_/g,' ')||'TACTICAL EXERCISE')} · ${escapeHTML(p.difficulty||'Practice')}</div><span class="tile-symbol">✧</span><h3>${escapeHTML(p.title)}</h3><p>${escapeHTML(p.objective)}</p><button class="text-button" data-start-exercise="${escapeHTML(p.id)}" data-kind="puzzle">Solve on the board <span>→</span></button></article>`).join('')}</div>`;}
  async function loadStudies(){const data=await api('/learning/studies');const studies=data.studies||[];state.contentRecords=studies;$('#content-view').innerHTML=`<div class="content-toolbar"><p class="muted">Position-based studies · No invented opening frequencies.</p><button class="secondary-button" data-action="import-pgn">Import a PGN study</button></div><div class="tile-grid">${studies.map(s=>`<article class="card content-tile"><div class="kicker">${escapeHTML(s.kind||'Study')}${s.eco?' · '+escapeHTML(s.eco):''}</div><span class="tile-symbol">${s.kind==='endgame'?'♔':'♘'}</span><h3>${escapeHTML(s.title)}</h3><p>${escapeHTML(Array.isArray(s.plans)?s.plans.join(' '):s.plans||s.objective||'Explore the position and its legal continuations.')}</p><button class="text-button" data-start-exercise="${escapeHTML(s.id)}" data-kind="study">Open study <span>→</span></button></article>`).join('')}</div>`;}
  async function startExercise(id,kind){
    if(!await requireSession())return;const exercise=state.contentRecords.find(r=>r.id===id);if(!exercise)return;
    const record={...exercise,kind};setGame(await api('/games',{method:'POST',body:{mode:'study',human_color:'white',time_seconds:0,increment_seconds:0,fen:exercise.fen}}));state.exercise=record;state.rotated=String(exercise.side_to_move||'').toLowerCase()==='black';await navigate('analysis');renderBoard();renderGame();$('#coach-output').hidden=false;$('#coach-output').innerHTML=`<p><strong>${escapeHTML(kind.toUpperCase())}</strong><br>${escapeHTML(exercise.body||exercise.objective||'Explore the legal position.')}</p>${exercise.plans?`<p>${escapeHTML(Array.isArray(exercise.plans)?exercise.plans.join(' '):exercise.plans)}</p>`:''}${kind==='study'&&(exercise.moves||exercise.solution)?.length?`<p class="analysis-meta">DEMONSTRATED UCI LINE: ${escapeHTML((exercise.moves||exercise.solution).join(' '))}</p><button class="secondary-button" id="play-study-line">Play demonstrated line</button>`:''}`;
    toast('Exercise ready. Play your line, then choose Check exercise.');
  }
  function renderExerciseAction(){
    let toolbar=$('#exercise-actions');
    if(!state.exercise){toolbar?.remove();return;}
    if(!toolbar){toolbar=document.createElement('div');toolbar.id='exercise-actions';toolbar.className='game-actions';$('.game-card').append(toolbar);}
    toolbar.innerHTML=`<button class="secondary-button" id="check-exercise">Check exercise</button>${state.exercise.kind==='puzzle'?'<button class="text-button" id="hint-exercise">Get a hint</button>':''}<button class="text-button" id="retry-exercise">Retry</button>`;
  }
  async function checkExercise(hint=false){
    const e=state.exercise;if(!e||!state.game)return;const moves=state.game.moves.map(m=>m.uci);
    try{let result;if(e.kind==='puzzle')result=await api('/puzzles/'+encodeURIComponent(e.id)+'/attempts',{method:'POST',body:{moves,hint}});else if(e.kind==='lesson')result=await api('/lessons/'+encodeURIComponent(e.id)+'/complete',{method:'POST',body:{moves}});else{toast('This is an open study. Request engine analysis to investigate your continuation.');return;}
      const message=result.hint||result.message||(result.correct||result.completed||result.status==='completed'?'Exercise completed and progress saved.':'Try another continuation.');toast(message,!(hint||result.correct||result.completed||result.status==='completed'));$('#coach-output').hidden=false;$('#coach-output').innerHTML=`<p><strong>${hint?'HINT':'EXERCISE RESULT'}</strong><br>${escapeHTML(message)}</p>`;
    }catch(err){toast(err.message,true);}
  }
  async function retryExercise(){const e=state.exercise;if(!e)return;setGame(await api('/games',{method:'POST',body:{mode:'study',time_seconds:0,increment_seconds:0,fen:e.fen}}));state.exercise=e;renderGame();renderBoard();}
  async function playStudyLine(){
    const exercise=state.exercise;if(!exercise||state.busy)return;
    if(state.game.moves.length){toast('Use Retry before playing the complete demonstrated line.');return;}
    state.busy=true;updateActions();
    try{for(const uci of exercise.moves||exercise.solution||[]){setGame(await api('/games/'+encodeURIComponent(gameId(state.game))+'/moves',{method:'POST',body:{uci,expected_version:state.game.version,request_id:crypto.randomUUID()}}));}toast('The server-validated study line is ready to replay.');}
    catch(e){toast(e.message,true);}finally{state.busy=false;updateActions();}
  }
  async function loadResearch(){
    const data=await api('/research/experiments');const experiments=data.experiments||[];
    $('#content-view').innerHTML=`<div class="status-note">Relevance scores rank computational attention; they are not calibrated probabilities or proven playing strength. A completed experiment can report a negative result.</div><form id="research-form" class="card inline-form"><label>Nodes per method<input name="nodes" type="number" min="2000" max="100000" value="20000" required></label><label>Reference nodes<input name="reference_nodes" type="number" min="4000" max="200000" value="40000" required></label><label>Random seed<input name="seed" type="number" min="0" value="7331" required></label><button class="primary-button" type="submit">Run controlled experiment <span>↗</span></button></form><div class="content-toolbar"><p class="muted">Training, validation, and held-out evidence stay attached to each experiment.</p><button class="secondary-button" data-action="rank-position">Rank current position</button></div><div id="relevance-ranking"></div><div id="research-records">${experimentRecords(experiments)}</div>`;
  }
  function experimentRecords(records){if(!records.length)return '<div class="empty-panel"><h2>Let the evidence lead.</h2><p>No experiment has been run. Choose a bounded budget to begin.</p></div>';return records.map(e=>`<article class="card study-detail"><div class="card-heading"><h2>Experiment ${escapeHTML(String(e.id).slice(0,12))}</h2><span class="pill">${escapeHTML(e.status)}</span></div>${e.result?renderExperimentResult(e.result):'<p class="muted">Execution evidence will appear when the job reaches a terminal state.</p>'}<div class="content-actions"><button class="text-button" data-refresh-experiment="${escapeHTML(e.id)}">Refresh evidence ↻</button>${!['completed','failed','cancelled','interrupted'].includes(String(e.status).toLowerCase())?`<button class="text-button" data-cancel-experiment="${escapeHTML(e.id)}">Cancel</button>`:''}</div></article>`).join('');}
  function renderExperimentResult(result){
    const summary=result.summary||{},rows=result.comparisons||result.rows||result.results||[];
    const names={conventional:'A · Conventional engine',uniform:'B · Uniform allocation',heuristic:'C · Heuristic relevance',learned:'D · Learned relevance'};
    const summaryRows=Object.entries(summary).filter(([,value])=>value&&typeof value==='object');
    return `<p>${escapeHTML(result.conclusion||result.disclaimer||'Measured research result; superiority is not assumed.').replace(/_/g,' ')}</p>`+
      (summaryRows.length?`<div style="overflow:auto"><table class="content-table"><thead><tr><th>METHOD</th><th>REFERENCE AGREEMENT</th><th>ACTUAL NODES</th><th>SECONDS</th><th>CP REGRET</th></tr></thead><tbody>${summaryRows.map(([method,r])=>`<tr><td><strong>${escapeHTML(names[method]||method)}</strong><small>${escapeHTML(r.positions)} held-out positions</small></td><td>${Number.isFinite(r.agreement)?(100*r.agreement).toFixed(1)+'%':'—'}</td><td>${escapeHTML(formatNumber(r.nodes))}</td><td>${Number.isFinite(r.seconds)?r.seconds.toFixed(3):'—'}</td><td>${Number.isFinite(r.mean_cp_regret)?r.mean_cp_regret.toFixed(1):'Mate / no CP comparison'}</td></tr>`).join('')}</tbody></table></div>`:'')+
      `<p class="analysis-meta">${escapeHTML(result.budget_policy||'Reported actual cost can differ from the requested engine budget.')}</p>`+
      (rows.length?`<details class="record-details"><summary>Compare individual held-out positions</summary><div style="overflow:auto"><table class="content-table"><thead><tr><th>METHOD / POSITION</th><th>CHOSEN</th><th>REFERENCE</th><th>NODES</th><th>SECONDS</th><th>AGREEMENT</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escapeHTML(names[r.policy]||r.method||r.system||'Recorded result')}<small>${escapeHTML(String(r.position_id||r.id||'').slice(0,20))}</small></td><td>${escapeHTML(r.chosen_move||r.bestmove||r.selected_move||'—')}</td><td>${escapeHTML(r.reference_move||'—')}</td><td>${escapeHTML(r.actual_nodes??r.nodes??'—')}</td><td>${Number.isFinite(r.elapsed_seconds)?r.elapsed_seconds.toFixed(3):'—'}</td><td>${r.agreement===true?'Match':r.agreement===false?'Different':'—'}</td></tr>`).join('')}</tbody></table></div></details>`:'')+
      `<details class="record-details"><summary>Inspect full recorded research evidence</summary><pre>${escapeHTML(JSON.stringify(result,null,2))}</pre></details>`;
  }
  async function startResearch(event){event.preventDefault();if(!await requireSession())return;const form=new FormData(event.target);const body=Object.fromEntries([...form].map(([k,v])=>[k,Number(v)]));const submit=event.target.querySelector('button');submit.disabled=true;try{const job=await api('/research/experiments',{method:'POST',body});toast('Controlled experiment started.');await refreshExperiment(job.id);}catch(e){toast(e.message,true);}finally{submit.disabled=false;}}
  async function refreshExperiment(id){try{const record=await api('/research/experiments/'+encodeURIComponent(id));$('#research-records').innerHTML=experimentRecords([record]);if(!['completed','failed','cancelled','canceled','interrupted'].includes(String(record.status).toLowerCase())){clearTimeout(state.researchTimer);state.researchTimer=setTimeout(()=>{if(state.view==='research')refreshExperiment(id);},1200);}}catch(e){toast(e.message,true);}}
  async function rankPosition(){try{const data=await api('/research/relevance?fen='+encodeURIComponent(displayedFen()));$('#relevance-ranking').innerHTML=`<article class="card study-detail"><h2>Candidate relevance</h2><p>${escapeHTML(data.disclaimer||'Experimental ranking of all legal moves.')}</p><div style="max-height:350px;overflow:auto"><table class="content-table"><thead><tr><th>LEGAL MOVE</th><th>HEURISTIC</th><th>LEARNED</th></tr></thead><tbody>${(data.rows||[]).map(r=>`<tr><td>${escapeHTML(r.san||r.uci)}</td><td>${Number.isFinite(r.heuristic_score)?r.heuristic_score.toFixed(3):'—'}</td><td>${Number.isFinite(r.learned_score)?r.learned_score.toFixed(3):'—'}</td></tr>`).join('')}</tbody></table></div><p class="analysis-meta">${escapeHTML(data.policy_status)}</p></article>`;}catch(e){toast(e.message,true);}}
  async function loadTournaments(){const data=await api('/tournaments');$('#content-view').innerHTML=`<div class="status-note">Local engine results apply only to the recorded opponents, positions, and budgets. “Elo 5000” is the product identity, not an achieved or official rating.</div><form id="tournament-form" class="card inline-form"><label>Nodes per move<input name="nodes" type="number" min="1000" max="50000" value="3000" required></label><label>Maximum plies<input name="max_plies" type="number" min="8" max="300" value="120" required></label><button type="submit" class="primary-button">Start paired tournament <span>↗</span></button></form><div id="tournament-records">${tournamentRecords(data.tournaments||[])}</div>`;}
  function tournamentRecords(records){
    if(!records.length)return '<div class="empty-panel"><h2>A fair match. A measured result.</h2><p>No tournament has been run. Paired games reverse colors under a fixed node budget.</p></div>';
    return records.map(t=>{
      const r=t.result;
      const interval=r?.uncertainty;
      const uncertainty=interval&&typeof interval==='object'&&Number.isFinite(interval.score_lower)&&Number.isFinite(interval.score_upper)?`Exploratory score interval: ${(100*interval.score_lower).toFixed(1)}%–${(100*interval.score_upper).toFixed(1)}%.`:'Small local samples have substantial statistical uncertainty.';
      return `<article class="card study-detail"><div class="card-heading"><h2>Tournament ${escapeHTML(String(t.id).slice(0,12))}</h2><span class="pill">${escapeHTML(t.status)}</span></div>`+
        (r?`<div class="stats-grid"><div class="stat-card"><small>Wins</small><strong>${escapeHTML(r.wins??'—')}</strong></div><div class="stat-card"><small>Draws</small><strong>${escapeHTML(r.draws??'—')}</strong></div><div class="stat-card"><small>Losses</small><strong>${escapeHTML(r.losses??'—')}</strong></div><div class="stat-card"><small>Relative Elo Δ</small><strong>${escapeHTML(typeof r.rating_estimate==='number'?(r.rating_estimate>=0?'+':'')+r.rating_estimate.toFixed(0):'—')}</strong></div></div><p>${escapeHTML(uncertainty)} ${escapeHTML(r.rating_reference||'')}</p>`+
        `<div style="overflow:auto"><table class="content-table"><thead><tr><th>PAIRED GAME</th><th>RESULT</th><th>MOVES</th><th>TERMINATION</th><th>NODES</th></tr></thead><tbody>${(r.games||[]).map((g,index)=>`<tr><td><strong>${index+1} · ${g.color_reversed?'Colors reversed':'First colors'}</strong><small>${escapeHTML(g.white)} / ${escapeHTML(g.black)}</small></td><td>${escapeHTML(g.result)}</td><td>${escapeHTML(g.moves?.length??'—')}</td><td>${escapeHTML(String(g.termination||'').replace(/_/g,' '))}${g.error?`<small>${escapeHTML(g.error)}</small>`:''}</td><td>${escapeHTML(formatNumber(g.nodes))}</td></tr>`).join('')}</tbody></table></div><p class="analysis-meta">${escapeHTML(r.limitation||'')}</p><details class="record-details"><summary>Inspect paired-game evidence and PGNs</summary><pre>${escapeHTML(JSON.stringify(r,null,2))}</pre></details>`:'<p class="muted">Games are running under the recorded budget.</p>')+
        `<div class="content-actions"><button class="text-button" data-refresh-tournament="${escapeHTML(t.id)}">Refresh results ↻</button>${!['completed','failed','cancelled','interrupted'].includes(String(t.status).toLowerCase())?`<button class="text-button" data-cancel-tournament="${escapeHTML(t.id)}">Cancel</button>`:''}</div></article>`;
    }).join('');
  }
  async function startTournament(event){event.preventDefault();if(!await requireSession())return;const form=new FormData(event.target);const body={nodes:Number(form.get('nodes')),max_plies:Number(form.get('max_plies')),paired:true};const submit=event.target.querySelector('button');submit.disabled=true;try{const job=await api('/tournaments',{method:'POST',body});toast('Paired tournament started.');await refreshTournament(job.id);}catch(e){toast(e.message,true);}finally{submit.disabled=false;}}
  async function refreshTournament(id){try{const record=await api('/tournaments/'+encodeURIComponent(id));$('#tournament-records').innerHTML=tournamentRecords([record]);if(!['completed','failed','cancelled','canceled','interrupted'].includes(String(record.status).toLowerCase())){clearTimeout(state.tournamentTimer);state.tournamentTimer=setTimeout(()=>{if(state.view==='tournaments')refreshTournament(id);},1200);}}catch(e){toast(e.message,true);}}
  async function cancelResearch(kind,id){try{await api((kind==='experiment'?'/research/experiments/':'/tournaments/')+encodeURIComponent(id)+'/cancel',{method:'POST',body:{}});toast('Cancellation requested.');if(kind==='experiment')await refreshExperiment(id);else await refreshTournament(id);}catch(e){toast(e.message,true);}}
  async function discoverStatus(){
    try{
      const [status,engines]=await Promise.all([api('/system/status',{quietAuth:true}),api('/engines',{quietAuth:true})]);state.engines=engines.engines||[];
      $('#system-dot').style.background='var(--success)';$('#system-label').innerHTML='Your local laboratory is online<small>LOCAL • DEVELOPMENT PREVIEW</small>';
      const available=state.engines.filter(e=>e.available);if(available.length){$('#engine-state').textContent=available.some(e=>e.status==='VERIFIED')?'VERIFIED ENGINE':'ENGINE AVAILABLE';$('#engine-state').className='pill';}
      if(!$('#new-skill')){
        const row=document.createElement('div');row.className='form-grid';row.innerHTML=`<label>Engine<select id="new-engine">${available.length?available.map(e=>`<option value="${escapeHTML(e.id||e.sha256||'')}">${escapeHTML(e.name||'Local UCI engine')}</option>`).join(''):'<option value="">No available local engine</option>'}</select></label><label>Skill level<select id="new-skill"><option value="20">20 · Full strength</option><option value="10">10 · Practice</option><option value="0">0 · Gentle practice</option></select></label>`;$('#new-mode').closest('label').after(row);
      }
      return status;
    }catch{ $('#system-dot').style.background='var(--danger)';$('#system-label').innerHTML='Chess service is offline<small>START THE LOCAL BACKEND</small>'; }
  }
  function installEvents(){
    $('#theme-toggle').addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;try{localStorage.setItem('chesselo5000.theme',theme);}catch{}});
    $('#menu-toggle').addEventListener('click',()=>$('.sidebar').classList.toggle('open'));
    $('#account-button').addEventListener('click',()=>state.user?toast('Signed in to your independent chess studio.'):showLogin());
    $('#close-login').addEventListener('click',()=>closeDialog('login-dialog'));
    $('#login-form').addEventListener('submit',async event=>{event.preventDefault();$('#login-error').textContent='';const button=event.target.querySelector('button[type=submit]');button.disabled=true;try{const s=await api('/session',{method:'POST',body:{password:$('#owner-password').value},quietAuth:true});setUser(s.user,s.csrf_token);$('#owner-password').value='';closeDialog('login-dialog');toast('Your chess studio is open.');await navigate(state.view);}catch(e){$('#login-error').textContent=e.message;}finally{button.disabled=false;}});
    $('#new-game-button').addEventListener('click',async()=>{if(await requireSession())openDialog('new-game-dialog');});
    $('#new-game-form').addEventListener('submit',newGame);
    $('#rotate-board').addEventListener('click',()=>{state.rotated=!state.rotated;renderBoard();renderGame();});
    $('#copy-fen').addEventListener('click',copyFen);$('#undo-move').addEventListener('click',()=>gameAction('undo'));$('#engine-reply').addEventListener('click',requestEngineReply);$('#resign-game').addEventListener('click',()=>gameAction('resign'));
    $('#restart-game').addEventListener('click',restartGame);
    $('#draw-game').addEventListener('click',()=>{const g=state.game;if(!g)return;const claims=g.claimable_draws;const canClaim=Array.isArray(claims)?claims.length>0:!!claims&&Object.values(claims).some(Boolean);gameAction('draw',{kind:canClaim?'claim':g.draw_offer?'accept':'offer'});});
    $('#analyze-position').addEventListener('click',runAnalysis);$('#cancel-analysis').addEventListener('click',cancelAnalysis);$('#coach-position').addEventListener('click',explainPosition);$('#branch-position').addEventListener('click',createBranch);
    $('#text-form').addEventListener('submit',async event=>{event.preventDefault();const button=$('#text-dialog-submit');button.disabled=true;try{await state.textAction?.($('#text-dialog-value').value);}catch(e){toast(e.message,true);}finally{button.disabled=false;}});
    $('#promotion-options').addEventListener('click',event=>{const move=event.target.closest('[data-promotion]')?.dataset.promotion;if(move){closeDialog('promotion-dialog');submitMove(move);}});
    const board=$('#chessboard');
    board.addEventListener('pointerdown',event=>{const sq=event.target.closest('[data-square]');if(!sq||event.button!==0)return;state.pointer={square:sq.dataset.square,x:event.clientX,y:event.clientY,id:event.pointerId};sq.focus({preventScroll:true});});
    board.addEventListener('pointerup',event=>{const p=state.pointer;if(!p)return;state.pointer=null;const sq=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-square]');if(!sq)return;const dragged=Math.hypot(event.clientX-p.x,event.clientY-p.y)>7;if(dragged){state.selected=p.square;chooseSquare(sq.dataset.square);}else chooseSquare(sq.dataset.square);});
    board.addEventListener('pointercancel',()=>{state.pointer=null;});
    board.addEventListener('click',event=>{if(event.detail===0){const sq=event.target.closest('[data-square]');if(sq)chooseSquare(sq.dataset.square);}});
    board.addEventListener('keydown',event=>{const sq=event.target.closest('[data-square]');if(!sq)return;const keys={ArrowLeft:-1,ArrowRight:1,ArrowUp:-8,ArrowDown:8};if(Object.hasOwn(keys,event.key)){event.preventDefault();const coords=boardCoordinates(state.rotated),at=coords.indexOf(sq.dataset.square),next=at+keys[event.key];if(next>=0&&next<64&&(!['ArrowLeft','ArrowRight'].includes(event.key)||Math.floor(next/8)===Math.floor(at/8))){sq.tabIndex=-1;const target=board.querySelector('[data-square="'+coords[next]+'"]');target.tabIndex=0;target.focus();}}else if(event.key==='Escape'){state.selected=null;renderBoard();}});
    document.addEventListener('click',async event=>{
      const target=event.target.closest('button,[data-view]');if(!target)return;
      try{
        if(target.dataset.close){closeDialog(target.dataset.close);return;}
        if(target.dataset.view){await navigate(target.dataset.view);return;}
        if(target.dataset.retry){await navigate(target.dataset.retry);return;}
        if(target.dataset.replay){replay(target.dataset.replay);return;}
        if(target.dataset.ply){replay(target.dataset.ply);return;}
        if(target.dataset.openGame){state.exercise=null;setGame(await api('/games/'+encodeURIComponent(target.dataset.openGame)));await navigate('analysis');return;}
        if(target.dataset.exportGame){await exportPGN(target.dataset.exportGame);return;}
        if(target.dataset.lesson){showLesson(target.dataset.lesson);return;}
        if(target.dataset.startExercise){await startExercise(target.dataset.startExercise,target.dataset.kind);return;}
        if(target.dataset.refreshExperiment){await refreshExperiment(target.dataset.refreshExperiment);return;}
        if(target.dataset.refreshTournament){await refreshTournament(target.dataset.refreshTournament);return;}
        if(target.dataset.cancelExperiment){await cancelResearch('experiment',target.dataset.cancelExperiment);return;}
        if(target.dataset.cancelTournament){await cancelResearch('tournament',target.dataset.cancelTournament);return;}
        if(target.id==='check-exercise'){await checkExercise();return;}if(target.id==='hint-exercise'){await checkExercise(true);return;}if(target.id==='retry-exercise'){await retryExercise();return;}if(target.id==='play-study-line'){await playStudyLine();return;}
        if(target.dataset.action==='import-pgn')await importPGN();else if(target.dataset.action==='export-current')await exportPGN();else if(target.dataset.action==='rank-position')await rankPosition();
      }catch(e){toast(e.message,true);}
    });
    document.addEventListener('submit',event=>{if(event.target.id==='research-form')startResearch(event);else if(event.target.id==='tournament-form')startTournament(event);});
    window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
    document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',event=>{if(event.target===d&&d.id!=='promotion-dialog')d.close();}));
  }
  async function initialize(){
    try{const theme=localStorage.getItem('chesselo5000.theme');if(['light','dark'].includes(theme))document.documentElement.dataset.theme=theme;}catch{}
    installEvents();renderBoard();renderGame();updateActions();
    await Promise.all([startSession(),discoverStatus()]);
    if(state.user){try{const id=localStorage.getItem('chesselo5000.game');if(id)setGame(await api('/games/'+encodeURIComponent(id),{quietAuth:true}));}catch{}}
    const requested=location.hash.slice(1)||config.defaultView||'play';await navigate(requested);
    setInterval(renderClocks,250);
  }
  initialize().catch(e=>toast(e.message,true));
})();
