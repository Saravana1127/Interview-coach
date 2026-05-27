/**
 * app.js — AI Placement Portal · Main Application
 *
 * Depends on (must be loaded first):
 *   proctoring.js  → window.ProctoringManager
 *   webrtc.js      → window.WebRTCManager
 *
 * Responsibilities:
 *   • Global state management (HR session + MCQ session)
 *   • All fetch() calls to the FastAPI backend
 *   • HR behavioral interview flow (start → chat → evaluate → report)
 *   • MCQ quiz flow (generate → answer → submit → report)
 *   • Settings management (localStorage)
 *   • UI helpers (page navigation, banners, score animations)
 */

(function () {
  'use strict';

  // =========================================================================
  // CONFIGURATION
  // =========================================================================

  const DEFAULT_CFG = {
    apiBase:    'http://localhost:8000',
    model:      'llama3',
    totalTurns: 7,
    proctor:    true,
    tts:        true,
  };

  let Cfg = Object.assign({}, DEFAULT_CFG, _loadCfg());

  // Expose config globally so proctoring.js can read the API base URL
  window._AIP_CFG = Cfg;

  function _loadCfg() {
    try { return JSON.parse(localStorage.getItem('aip_cfg')  '{}'); }
    catch { return {}; }
  }

  function _saveCfg() {
    localStorage.setItem('aip_cfg', JSON.stringify(Cfg));
    window._AIP_CFG = Cfg;
  }

  // =========================================================================
  // STATE
  // =========================================================================

  function _freshState() {
    return {
      phase: 'landing',

      // -- HR mode --
      name:               '',
      jobTitle:           '',
      turn:               0,
      totalTurns:         Cfg.totalTurns,
      conv:               [],   // Full message array sent to LLM
      chatHistory:        [],   // { role, text, time } — for UI
      assistantQuestions: [],
      candidateAnswers:   [],
      feedback:           null,
      startTime:          null,

      // -- MCQ mode --
      mcq: {
        name:          '',
        topic:         '',
        questions:     [],
        currentIndex:  0,
        timeLimit:     600,
        timeLeft:      600,
        timerInterval: null,
        startTime:     null,
        endTime:       null,
      },
    };
  }

  let S = _freshState();

  function _saveState() {
    try { sessionStorage.setItem('aip_s', JSON.stringify(S)); } catch (_) { }
  }

  // =========================================================================
  // DOM HELPERS
  // =========================================================================

  const $ = id => document.getElementById(id);

  function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function autoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }

  function animNum(el, from, to, dur) {
    const start = performance.now();
    (function tick(now) {
      const p = Math.min((now - start) / dur, 1);
      el.textContent = Math.round(from + (to - from) * p);
      if (p < 1) requestAnimationFrame(tick);
    })(start);
  }

  let _bannerTimer;
  function showBanner(msg, cls, dur = 3000) {
    const b = $('warnBanner');
    b.textContent = msg;
    b.className   = `warning-banner ${cls}`;
    b.classList.remove('hidden');
    clearTimeout(_bannerTimer);
    _bannerTimer = setTimeout(() => b.classList.add('hidden'), dur);
  }

  function showErr(msg) {
    $('errMsg').textContent = msg;
    $('errOvl').classList.remove('hidden');
  }

  // =========================================================================
  // PAGE NAVIGATION
  // =========================================================================

  const PAGES = {
    landing:   $('pgLand'),
    interview: $('pgInterview'),
    report:    $('pgReport'),
    mcq:       $('pgMcq'),
    mcqReport: $('pgMcqReport'),
  };

  function showPage(name) {
    Object.values(PAGES).forEach(p => {
      p.classList.add('hidden');
      p.classList.remove('fade-in');
    });
    PAGES[name].classList.remove('hidden');
    requestAnimationFrame(() => PAGES[name].classList.add('fade-in'));

    S.phase = name;
    $('intStrip').classList.toggle('hidden', name !== 'interview' && name !== 'mcq');
    $('sessionInfo').style.display = (name === 'interview'  name === 'report') ? 'flex' : 'none';
    _saveState();
  }

  // =========================================================================
  // MODE SELECTION  (called from HTML onclick)
  // =========================================================================

  function selectMode(mode) {
    $('modeSelector').classList.add('hidden');
    $('hrSetup').classList.toggle('hidden',  mode !== 'hr');
    $('mcqSetup').classList.toggle('hidden', mode !== 'mcq');
  }
  window.selectMode = selectMode;

  function backToModes() {
    $('modeSelector').classList.remove('hidden');
    $('hrSetup').classList.add('hidden');
    $('mcqSetup').classList.add('hidden');
  }
  window.backToModes = backToModes;

  // =========================================================================
  // SETTINGS
  // =========================================================================

  function togSet() { $('setOvl').classList.toggle('hidden'); }
  window.togSet = togSet;
  $('gearBtn').addEventListener('click', togSet);

  function _loadSettingsUI() {
    $('sApiBase').value   = Cfg.apiBase;
    $('sMod').value       = Cfg.model;
    $('sTurns').value     = Cfg.totalTurns;
    $('sPr').checked      = Cfg.proctor;
    $('sTTS').checked     = Cfg.tts;
  }

  function saveSettings() {
    Cfg.apiBase    = $('sApiBase').value.trim()  DEFAULT_CFG.apiBase;
    Cfg.model      = $('sMod').value.trim()      DEFAULT_CFG.model;
    Cfg.totalTurns = +$('sTurns').value;
    Cfg.proctor    = $('sPr').checked;
    Cfg.tts        = $('sTTS').checked;
    S.totalTurns   = Cfg.totalTurns;
    _saveCfg();
    togSet();
  }
  window.saveSettings = saveSettings;

  // =========================================================================
  // BACKEND API
  // =========================================================================

  async function apiPost(endpoint, body) {
    const res = await fetch(`${Cfg.apiBase}${endpoint}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ...body, model: Cfg.model }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail  err.error  `HTTP ${res.status}`);
    }
    return res.json();
  }

  // =========================================================================
  // WEBRTC + PROCTORING INSTANCES
  // =========================================================================

  const rtc     = new window.WebRTCManager();
  const proctor = new window.ProctoringManager();

  // Proctoring events → update UI banner + counter strip
  document.addEventListener('proctor-event', (e) => {
    if (!Cfg.proctor) return;
    const { type } = e.detail;
    const msgs = {
      tab_switch:  'Tab switch detected & logged!',
      paste:       'Paste detected & logged!',
      mouse_leave: 'Mouse left the interview window',
    };
    showBanner(msgs[type]  'Proctoring event', type === 'mouse_leave' ? 'amber' : 'red');
    _updateIntegrityUI();
  });

  function _updateIntegrityUI() {
    const s = proctor.getStats();
    $('cTab').textContent   = s.tabs;
    $('cPaste').textContent = s.pastes;
    $('cMouse').textContent = s.mouse;
    $('mTab').classList.toggle('w',   s.tabs   > 2);
    $('mPaste').classList.toggle('w', s.pastes > 0);
    $('mMouse').classList.toggle('w', s.mouse  > 3);
  }

  // =========================================================================
  // HR BEHAVIORAL INTERVIEW
  // =========================================================================

  let _waitingAI = false;

  $('btnStart').addEventListener('click', async () => {
    const nm  = $('inName').value.trim();
    const job = $('inJob').value.trim();

    if (!nm)  { $('inName').style.borderColor = 'var(--danger)'; $('inName').focus(); return; }
    if (!job) { $('inJob').style.borderColor  = 'var(--danger)'; $('inJob').focus();  return; }
    $('inName').style.borderColor = '';
    $('inJob').style.borderColor  = '';

    // Reset state
    S                   = _freshState();
    S.name              = nm;
    S.jobTitle          = job;
    S.totalTurns        = Cfg.totalTurns;
    S.startTime         = Date.now();

    // Top-bar labels
    $('sName').innerHTML = `<b>${esc(nm)}</b>`;
    $('sJob').innerHTML  = `Role: <b>${esc(job)}</b>`;
    _updateTurnUI();
    showPage('interview');
    $('chatMessages').innerHTML = '';

    // Camera
    const camOk = await rtc.startCamera($('camVideo'));
    $('camOff').classList.toggle('hidden',  camOk);
    $('camVideo').classList.toggle('hidden', !camOk);

    // STT
    rtc.initSTT(
      (text) => {
        $('chatInput').value = text;
        autoGrow($('chatInput'));
        $('sendBtn').disabled = !text.trim();
      },
      () => $('micBtn').classList.remove('active')
    );

    // Proctoring
    proctor.reset();
    if (Cfg.proctor) {
      proctor.start(
        () => S.phase,
        () => ({ turn: S.turn })
      );
    }

    // System prompt (Sarah persona)
    S.conv.push({
      role:    'system',
      content: `You are "Sarah," a Senior HR Manager conducting a live, 1-on-1 behavioral interview with a candidate named "${nm}" for the "${job}" role. Your objective is to assess their communication skills, cultural fit, confidence, and professionalism.

RULES:
- Speak directly, warmly, but professionally.
- You MUST start by saying: "Hello ${nm}, it's great to meet you! To start us off, could you please introduce yourself and walk me through your background?"
- After the candidate responds, ask standard HR behavioral questions. Ask ONE question at a time.
- Be conversational — briefly acknowledge their previous answer before the next question.
- This interview has exactly ${S.totalTurns} turns.
- On the FINAL turn (turn ${S.totalTurns}), after they answer, conclude: "Thank you for your time today, ${nm}. We will review your profile and get back to you. It was wonderful speaking with you!"
- Keep each response concise — 2–4 sentences maximum.`,
    });

    await _getAssistantResponse();
  });

  function _updateTurnUI() {
    const done = S.turn;
    $('turnCount').textContent  = `${done} / ${S.totalTurns}`;
    $('turnFill').style.width   = `${(done / S.totalTurns) * 100}%`;
    $('turnPillTxt').textContent = `Turn ${Math.min(done + 1, S.totalTurns)}/${S.totalTurns}`;
  }

  async function _getAssistantResponse() {
    _waitingAI = true;
    $('sendBtn').disabled       = true;
    $('chatInput').disabled     = true;
    $('assistantStatusTxt').textContent = 'Sarah is typing…';
    $('assistantDot').classList.remove('idle');
    _showTyping();

    try {
      const isLast = S.turn + 1 >= S.totalTurns;
      const prompt  = S.turn === 0
        ? `Begin the interview. This is turn 1 of ${S.totalTurns}. Greet the candidate and ask them to introduce themselves.`
        : `The candidate just responded. This is turn ${S.turn + 1} of ${S.totalTurns}.${
            isLast
              ? ' This is the FINAL turn. Acknowledge their answer briefly, then deliver your closing statement.'
              : ' Briefly acknowledge their answer, then ask the next behavioral question. ONE question only.'
          }`;

      S.conv.push({ role: 'user', content: prompt });

      const data  = await apiPost('/api/chat', { messages: S.conv, temperature: 0.7 });
      const reply = data.choices?.[0]?.message?.content  '';

      S.conv.push({ role: 'assistant', content: reply });
      _hideTyping();
      _addChatMessage('assistant', reply);
      S.assistantQuestions.push(reply);

      // TTS
      if (Cfg.tts) {
        rtc.speak(reply, {
          onStart: () => {
            $('assistantWrap').classList.add('speaking');
            $('assistantStatusTxt').textContent = 'Speaking…';
          },
          onEnd: () => {
            $('assistantWrap').classList.remove('speaking');
            if (S.turn < S.totalTurns) {
              $('assistantStatusTxt').textContent = 'Your turn';
              $('assistantDot').classList.add('idle');
            }
          },
        });
      } else {
        $('assistantStatusTxt').textContent = 'Your turn';
        $('assistantDot').classList.add('idle');
      }

      // Check if interview is over
      if (S.turn >= S.totalTurns) {
        $('chatInput').disabled = true;
        $('sendBtn').disabled   = true;
        $('chatHint').textContent = 'Interview concluded. Generating your evaluation report…';
        _waitingAI = false;
        setTimeout(_getHRFeedback, 2500);
        return;
      }

      _waitingAI            = false;
      $('chatInput').disabled = false;
      $('chatInput').focus();
      $('sendBtn').disabled   = true;
      _saveState();

    } catch (err) {
      _hideTyping();
      showErr(err.message);
      _waitingAI            = false;
      $('chatInput').disabled = false;
    }
  }

  // ---- Send answer ----
  $('sendBtn').addEventListener('click', _sendAnswer);
  $('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!$('sendBtn').disabled) _sendAnswer();
    }
  });
  $('chatInput').addEventListener('input', function () {
    autoGrow(this);
    $('sendBtn').disabled = !this.value.trim()  _waitingAI;
  });

  async function _sendAnswer() {
    const text = $('chatInput').value.trim();
    if (!text  _waitingAI) return;

    if (rtc.isListening) {
      rtc.stopListening();
      $('micBtn').classList.remove('active');
    }

    _addChatMessage('candidate', text);
    S.candidateAnswers.push(text);
    S.turn++;
    _updateTurnUI();

    S.conv.push({ role: 'user', content: `[Candidate's response]: ${text}` });
    $('chatInput').value = '';
    autoGrow($('chatInput'));
    $('sendBtn').disabled = true;
    _saveState();

    await _getAssistantResponse();
  }

  // ---- Mic button ----
  $('micBtn').addEventListener('click', () => {
    if (!rtc.isListening) {
      rtc.startListening();
      $('micBtn').classList.add('active');
    } else {
      rtc.stopListening();
      $('micBtn').classList.remove('active');
    }
  });

  // ---- Chat rendering ----
  function _addChatMessage(role, text) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    S.chatHistory.push({ role, text, time });

    const container   = $('chatMessages');
    const msgDiv      = document.createElement('div');
    msgDiv.className  = `msg ${role}`;
    const letter      = role === 'assistant' ? 'S' : (S.name.charAt(0).toUpperCase()  'C');
    const displayName = role === 'assistant' ? 'Sarah' : S.name;

    msgDiv.innerHTML = `
      <div class="msg-avatar">${letter}</div>
      <div class="msg-body">
        <div class="msg-name">${esc(displayName)}</div>
        <div class="msg-bubble">${esc(text)}</div>
        <div class="msg-time">${time}</div>
      </div>`;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
  }

  function _showTyping() {
    const container  = $('chatMessages');
    const div        = document.createElement('div');
    div.className    = 'msg assistant';
    div.id           = 'typingMsg';
    div.innerHTML    = `
      <div class="msg-avatar">S</div>
      <div class="msg-body">
        <div class="msg-name">Sarah</div>
        <div class="msg-bubble">
          <div class="typing-indicator">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>
      </div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  function _hideTyping() {
    const t = $('typingMsg');
    if (t) t.remove();
  }

  // ---- HR Evaluation ----
  async function _getHRFeedback() {
    $('assistantStatusTxt').textContent = 'Generating report…';
    const stats = proctor.getStats();

    try {
      const feedback = await apiPost('/api/hr/evaluate', {
        name:               S.name,
        jobTitle:           S.jobTitle,
        assistantQuestions: S.assistantQuestions,
        candidateAnswers:   S.candidateAnswers,
        totalTurns:         S.totalTurns,
        integrity:          { tabs: stats.tabs, pastes: stats.pastes, mouse: stats.mouse },
      });
      S.feedback = feedback;
      _saveState();
      _renderHRReport();
    } catch (_) {
      S.feedback = _hrFallback();
      _renderHRReport();
    }
  }

  function _hrFallback() {
    return {
      communicationScore:   60,
      communicationComment: 'Completed the interview. Review transcript for details.',
      culturalFitScore:     60,
      culturalFitComment:   'Participated in all turns. Consider using the STAR method.',
      confidenceScore:      60,
      confidenceComment:    'Showed willingness to engage.',
      overallScore:         60,
      hiringVerdict:        'Maybe',
      strengths:    ['Completed all turns', 'Engaged with the interviewer', 'Showed effort'],
      improvements: ['Use the STAR method', 'Provide specific examples', 'Practice conciseness'],
      turnFeedback: S.assistantQuestions.map((q, i) => ({
        turn:       i + 1,
        question:   q.substring(0, 120),
        assessment: S.candidateAnswers[i] ? 'Response provided' : 'No response',
      })),
    };
  }

  function _renderHRReport() {
    const fb = S.feedback;
    showPage('report');
    rtc.cancelSpeech();

    $('rMeta').textContent = `${S.name} · ${S.jobTitle} · ${new Date().toLocaleDateString()} · ${S.totalTurns} turns`;

    // Eval cards
    $('evalGrid').innerHTML = `
      <div class="eval-card comm">
        <div class="eval-icon">Comm</div>
        <div class="eval-score" id="commScore">0</div>
        <div class="eval-label">Communication &amp; Clarity</div>
        <div class="eval-bar"><div class="eval-fill" id="commFill" style="width:0%"></div></div>
        <div class="eval-comment">${esc(fb.communicationComment  '')}</div>
      </div>
      <div class="eval-card culture">
        <div class="eval-icon">Fit</div>
        <div class="eval-score" id="cultureScore">0</div>
        <div class="eval-label">Cultural Fit &amp; Professionalism</div>
        <div class="eval-bar"><div class="eval-fill" id="cultureFill" style="width:0%"></div></div>
        <div class="eval-comment">${esc(fb.culturalFitComment  '')}</div>
      </div>
      <div class="eval-card conf">
        <div class="eval-icon">Conf</div>
        <div class="eval-score" id="confScore">0</div>
        <div class="eval-label">Confidence Matrix</div>
        <div class="eval-bar"><div class="eval-fill" id="confFill" style="width:0%"></div></div>
        <div class="eval-comment">${esc(fb.confidenceComment  '')}</div>
      </div>`;

    setTimeout(() => {
      animNum($('commScore'),    0, fb.communicationScore, 1200); $('commFill').style.width    = fb.communicationScore + '%';
      animNum($('cultureScore'), 0, fb.culturalFitScore,   1200); $('cultureFill').style.width = fb.culturalFitScore   + '%';
      animNum($('confScore'),    0, fb.confidenceScore,    1200); $('confFill').style.width    = fb.confidenceScore    + '%';
    }, 300);

    // Verdict badge
    const v  = (fb.hiringVerdict  '').toLowerCase();
    const vb = $('vBadge');
    vb.textContent = fb.hiringVerdict  '—';
    vb.className   = 'verdict-badge ' + (
      v.includes('strong') ? 'verdict-sh' :
      v.includes('no')     ? 'verdict-nh' :
      v.includes('maybe')  ? 'verdict-m'  : 'verdict-h'
    );

    // Strengths / Improvements
    $('tCol').innerHTML = `
      <div class="lc green"><h3>Strengths</h3><ul>${(fb.strengths     []).map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>
      <div class="lc red"><h3>Areas for Improvement</h3><ul>${(fb.improvements  []).map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;

    // Turn-by-turn
    const turnCards = $('turnCards');
    turnCards.innerHTML = '';
    (fb.turnFeedback  []).forEach((tf, i) => {
      turnCards.innerHTML += `
        <div class="turn-card">
          <div class="turn-header">
            <div class="turn-num">${tf.turn  i + 1}</div>
            <div class="turn-q">${esc(tf.question  S.assistantQuestions[i]?.substring(0, 120)  '')}</div>
          </div>
          <div class="turn-a">${esc(S.candidateAnswers[i]  '(no response)')}</div>
          <div class="turn-feedback">${esc(tf.assessment  '')}</div>
        </div>`;
    });

    // Integrity
    const ps       = proctor.getStats();
    const intScore = Math.max(0, 100 - ps.tabs * 10 - ps.pastes * 20 - ps.mouse * 3);
    $('iGrid').innerHTML = [
      { l: 'Tab Switches', v: ps.tabs,   b: ps.tabs   > 2 },
      { l: 'Paste Events', v: ps.pastes, b: ps.pastes > 0 },
      { l: 'Mouse Exits',  v: ps.mouse,  b: ps.mouse  > 3 },
      { l: 'Integrity Score', v: intScore, b: intScore < 70 },
    ].map(m => `<div class="ic ${m.b ? 'bad' : 'good'}"><div class="iv">${m.v}</div><div class="il">${m.l}</div></div>`).join('');

    if (Cfg.tts) {
      rtc.speak(`Your interview is complete. Overall score: ${fb.overallScore} out of 100. Verdict: ${fb.hiringVerdict}.`);
    }
  }

  // =========================================================================
  // MCQ QUIZ MODE
  // =========================================================================

  $('btnMcqStart').addEventListener('click', async () => {
    const name            = $('mcqName').value.trim();
    const topic           = $('mcqTopic').value.trim();
    const count           = +$('mcqCount').value;
    const timeLimitMins   = +$('mcqTime').value;

    if (!name)  { $('mcqName').style.borderColor  = 'var(--danger)'; $('mcqName').focus();  return; }
    if (!topic) { $('mcqTopic').style.borderColor = 'var(--danger)'; $('mcqTopic').focus(); return; }
    $('mcqName').style.borderColor  = '';
    $('mcqTopic').style.borderColor = '';

    S       = _freshState();
    S.mcq   = {
      name, topic, questions: [], currentIndex: 0,
      timeLimit: timeLimitMins * 60, timeLeft: timeLimitMins * 60,
      timerInterval: null, startTime: Date.now(), endTime: null,
    };

    $('mcqMetaName').textContent  = name;
    $('mcqMetaTopic').textContent = topic;
    $('mcqTimerTxt').textContent  = `${timeLimitMins}:00`;

    // Loading state
    $('mcqQNum').textContent  = 'Generating…';
    $('mcqQText').textContent = `Generating ${count} questions for "${topic}"…`;
    $('mcqOptions').innerHTML = `<div class="typing-indicator" style="margin:20px auto">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
    $('mcqPrev').disabled = true;
    $('mcqNext').disabled = true;
    $('mcqSubmit').classList.add('hidden');
    $('mcqDots').innerHTML = '';

    showPage('mcq');
    _updateIntegrityUI();

    // Proctoring
    proctor.reset();
    if (Cfg.proctor) {
      proctor.start(
        () => S.phase,
        () => ({ qIndex: S.mcq.currentIndex })
      );
    }

    // Generate questions via backend
    try {
      const data = await apiPost('/api/mcq/generate', { topic, count });
      S.mcq.questions = (data.questions  []).map(q => ({
        ...q, selected: null, timeSpent: 0,
      }));
      if (!S.mcq.questions.length) throw new Error('No questions returned.');
      _startMcqQuiz();
    } catch (err) {
      showErr('Failed to generate questions: ' + err.message);
      showPage('landing');
    }
  });

  function _startMcqQuiz() {
    S.mcq.currentIndex = 0;
    S.mcq.startTime    = Date.now();

    // Build dot nav
    const dots = $('mcqDots');
    dots.innerHTML = '';
    S.mcq.questions.forEach((_, i) => {
      const dot       = document.createElement('span');
      dot.className   = 'mcq-q-dot';
      dot.id          = `mcqDot-${i}`;
      dot.textContent = i + 1;
      dot.addEventListener('click', () => _mcqGoTo(i));
      dots.appendChild(dot);
    });

    // Countdown timer
    clearInterval(S.mcq.timerInterval);
    let lastTick = Date.now();
    S.mcq.timerInterval = setInterval(() => {
      S.mcq.timeLeft--;

      // Accumulate time on current question
      const now   = Date.now();
      const delta = Math.round((now - lastTick) / 1000);
      lastTick    = now;
      if (S.mcq.questions[S.mcq.currentIndex]) {
        S.mcq.questions[S.mcq.currentIndex].timeSpent += delta;
      }

      if (S.mcq.timeLeft <= 0) {
        S.mcq.timeLeft = 0;
        clearInterval(S.mcq.timerInterval);
        showBanner('Time limit reached! Submitting quiz.', 'red');
        mcqFinish();
        return;
      }

      const m = Math.floor(S.mcq.timeLeft / 60);
      const s = S.mcq.timeLeft % 60;
      $('mcqTimerTxt').textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
      $('mcqTimer').classList.toggle('warn', S.mcq.timeLeft <= 60);
    }, 1000);

    _renderMcqQuestion();
  }

  function _renderMcqQuestion() {
    const q = S.mcq.questions[S.mcq.currentIndex];
    if (!q) return;

    $('mcqQNum').textContent  = `Question ${S.mcq.currentIndex + 1} of ${S.mcq.questions.length}`;
    $('mcqQText').textContent = q.question;

    const opts = $('mcqOptions');
    opts.innerHTML = '';
    q.options.forEach((opt, idx) => {
      const btn        = document.createElement('div');
      btn.className    = 'mcq-opt';
      if (q.selected === idx) btn.classList.add('selected');
      btn.innerHTML    = `<span class="opt-letter">${String.fromCharCode(65 + idx)}</span><span class="opt-text">${esc(opt)}</span>`;
      btn.addEventListener('click', () => _mcqSelectOpt(idx));
      opts.appendChild(btn);
    });

    // Update dot states
    S.mcq.questions.forEach((qItem, i) => {
      const dot = $(`mcqDot-${i}`);
      if (!dot) return;
      dot.className = 'mcq-q-dot';
      if (i === S.mcq.currentIndex)     dot.classList.add('active');
      else if (qItem.selected !== null) dot.classList.add('answered');
    });

    const answered = S.mcq.questions.filter(qi => qi.selected !== null).length;
    $('mcqProgressFill').style.width = `${(answered / S.mcq.questions.length) * 100}%`;

    $('mcqPrev').disabled = S.mcq.currentIndex === 0;
    const isLast = S.mcq.currentIndex === S.mcq.questions.length - 1;
    $('mcqNext').classList.toggle('hidden',   isLast);
    $('mcqSubmit').classList.toggle('hidden', !isLast);
  }

  function _mcqSelectOpt(idx) {
    if (!S.mcq.questions[S.mcq.currentIndex]) return;
    S.mcq.questions[S.mcq.currentIndex].selected = idx;
    _renderMcqQuestion();
  }

  function mcqNav(dir) {
    const target = S.mcq.currentIndex + dir;
    if (target >= 0 && target < S.mcq.questions.length) _mcqGoTo(target);
  }
  window.mcqNav = mcqNav;

  function _mcqGoTo(idx) {
    if (idx >= 0 && idx < S.mcq.questions.length) {
      S.mcq.currentIndex = idx;
      _renderMcqQuestion();
    }
  }

  async function mcqFinish() {
    clearInterval(S.mcq.timerInterval);
    S.mcq.endTime = Date.now();
    proctor.stop();

    $('mcqQNum').textContent  = 'Submitting…';
    $('mcqQText').textContent = 'Evaluating your answers and generating your report…';
    $('mcqOptions').innerHTML = `<div class="typing-indicator" style="margin:20px auto">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
    $('mcqPrev').disabled = true;
    $('mcqNext').disabled = true;
    $('mcqSubmit').classList.add('hidden');

    const ps = proctor.getStats();
    try {
      const feedback = await apiPost('/api/mcq/evaluate', {
        name:      S.mcq.name,
        topic:     S.mcq.topic,
        questions: S.mcq.questions,
        integrity: { tabs: ps.tabs, pastes: ps.pastes, mouse: ps.mouse },
      });
      _renderMcqReport(feedback);
    } catch (_) {
      _renderMcqReport(_mcqFallback());
    }
  }
  window.mcqFinish = mcqFinish;

  function _mcqFallback() {
    const qs      = S.mcq.questions;
    const times   = qs.map(q => q.timeSpent);
    const correct = qs.filter(q => q.selected === q.correct).length;
    const pct     = Math.round((correct / qs.length) * 100);
    const verdict = pct >= 90 ? 'Expert' : pct >= 75 ? 'Proficient' : pct >= 50 ? 'Competent' : pct >= 35 ? 'Developing' : 'Needs Improvement';
    return {
      verdict,
      technicalFeedback:  `Scored ${pct}% on ${S.mcq.topic}.`,
      behavioralFeedback: 'Session completed. Review integrity metrics for more details.',
      timeAnalysis: {
        averageTime:  Math.round(times.reduce((a, b) => a + b, 0) / times.length)  0,
        fastestIndex: times.indexOf(Math.min(...times)),
        slowestIndex: times.indexOf(Math.max(...times)),
      },
      roadmap: [
        `Review core ${S.mcq.topic} concepts`,
        'Complete additional practice assessments',
        'Follow structured online courses',
        'Build real-world projects to solidify skills',
      ],
    };
  }

  function _renderMcqReport(fb) {
    showPage('mcqReport');

    const qs        = S.mcq.questions;
    const correct   = qs.filter(q => q.selected === q.correct).length;
    const incorrect = qs.filter(q => q.selected !== null && q.selected !== q.correct).length;
    const skipped   = qs.filter(q => q.selected === null).length;
    const scorePct  = Math.round((correct / qs.length) * 100);

    $('mcqRMeta').textContent = `${S.mcq.name} · ${S.mcq.topic} · ${new Date().toLocaleDateString()} · ${qs.length} questions`;

    // Animate score ring
    const ring          = $('mcqRingFill');
    const radius        = ring.r.baseVal.value;
    const circumference = 2 * Math.PI * radius;
    ring.style.strokeDasharray  = circumference;
    ring.style.strokeDashoffset = circumference;
    $('mcqScoreNum').textContent = '0%';

    setTimeout(() => {
      ring.style.strokeDashoffset = circumference - (scorePct / 100) * circumference;
      const startT = performance.now();
      (function tick(now) {
        const p = Math.min((now - startT) / 1200, 1);
        $('mcqScoreNum').textContent = Math.round(scorePct * p) + '%';
        if (p < 1) requestAnimationFrame(tick);
      })(startT);
    }, 300);

    // Stat grid
    $('mcqStatGrid').innerHTML = `
      <div class="mcq-stat"><span class="sv" style="color:var(--accent);font-size:1rem">${fb.verdict  'Competent'}</span><span class="sl">Verdict</span></div>
      <div class="mcq-stat"><span class="sv green">${correct}</span><span class="sl">Correct</span></div>
      <div class="mcq-stat"><span class="sv red">${incorrect}</span><span class="sl">Incorrect</span></div>
      <div class="mcq-stat"><span class="sv amber">${skipped}</span><span class="sl">Skipped</span></div>`;

    // Time analysis
    const ta       = fb.timeAnalysis  { averageTime: 0, fastestIndex: 0, slowestIndex: 0 };
    const duration = Math.round(((S.mcq.endTime  Date.now()) - S.mcq.startTime) / 1000);
    $('mcqTimeGrid').innerHTML = `
      <div class="mcq-time-card"><div class="tv">${ta.averageTime}s</div><div class="tl">Avg Time / Question</div></div>
      <div class="mcq-time-card"><div class="tv">${qs[ta.fastestIndex]?.timeSpent  0}s (Q${ta.fastestIndex + 1})</div><div class="tl">Fastest Question</div></div>
      <div class="mcq-time-card"><div class="tv">${qs[ta.slowestIndex]?.timeSpent  0}s (Q${ta.slowestIndex + 1})</div><div class="tl">Slowest Question</div></div>
      <div class="mcq-time-card"><div class="tv">${duration}s</div><div class="tl">Total Duration</div></div>`;

    // Integrity grid
    const ps       = proctor.getStats();
    const intScore = Math.max(0, 100 - ps.tabs * 10 - ps.pastes * 20 - ps.mouse * 3);
    $('mcqIGrid').innerHTML = [
      { l: 'Tab Switches', v: ps.tabs,   b: ps.tabs   > 2 },
      { l: 'Paste Events', v: ps.pastes, b: ps.pastes > 0 },
      { l: 'Mouse Exits',  v: ps.mouse,  b: ps.mouse  > 3 },
      { l: 'Integrity Score', v: intScore, b: intScore < 70 },
    ].map(m => `<div class="ic ${m.b ? 'bad' : 'good'}"><div class="iv">${m.v}</div><div class="il">${m.l}</div></div>`).join('');

    // AI feedback + roadmap
    const reviewContainer = $('mcqReviewCards');
    reviewContainer.innerHTML = '';

    const aiDiv       = document.createElement('div');
    aiDiv.className   = 'setup-card';
    aiDiv.style.cssText = 'margin-bottom:24px;width:auto;max-width:100%';
    aiDiv.innerHTML   = `
      <h3 style="font-size:1.05rem;font-weight:700;margin-bottom:12px;color:var(--accent)">AI Behavioral &amp; Technical Assessment</h3>
      <p style="font-size:.9rem;line-height:1.6;margin-bottom:10px"><b>Technical Knowledge:</b> ${esc(fb.technicalFeedback)}</p>
      <p style="font-size:.9rem;line-height:1.6;margin-bottom:${fb.roadmap ? '16px' : '0'}"><b>Behavioral &amp; Pacing:</b> ${esc(fb.behavioralFeedback)}</p>
      ${fb.roadmap ? `
        <h4 style="font-size:.9rem;font-weight:700;margin-bottom:10px;color:var(--accent2)">Personalised Learning Roadmap</h4>
        <ul style="list-style:none;padding:0;display:flex;flex-direction:column;gap:8px">
          ${(fb.roadmap  []).map((step, i) => `
            <li style="font-size:.85rem;color:var(--muted);padding:10px 14px;background:var(--card2);border-radius:8px;border-left:3px solid var(--accent)">
              <b>Step ${i + 1}:</b> ${esc(step)}
            </li>`).join('')}
        </ul>` : ''}`;
    reviewContainer.appendChild(aiDiv);

    // Per-question review
    qs.forEach((q, idx) => {
      const isCorrect = q.selected === q.correct;
      const isSkipped = q.selected === null;
      const cls       = isCorrect ? 'correct' : isSkipped ? 'skip' : 'wrong';

      const card      = document.createElement('div');
      card.className  = 'mcq-q-review';
      card.innerHTML  = `
        <div class="qr-head">
          <span class="qr-num ${cls}">${idx + 1}</span>
          <span class="qr-text">${esc(q.question)}</span>
        </div>
        <div style="margin-top:10px;font-size:.87rem;display:flex;flex-direction:column;gap:6px">
          <div>• <b>Your Answer:</b>
            <span style="color:${isCorrect ? 'var(--success)' : isSkipped ? 'var(--muted)' : 'var(--danger)'}">
              ${q.selected !== null ? esc(q.options[q.selected]) : '(No answer selected)'}
            </span>
          </div>
          ${!isCorrect ? `<div>• <b>Correct Answer:</b> <span style="color:var(--success)">${esc(q.options[q.correct])}</span></div>` : ''}
          <div>• <b>Time Spent:</b> ${q.timeSpent}s</div>
        </div>
        <div class="qr-detail"><b>Explanation:</b> ${esc(q.explanation)}</div>`;
      reviewContainer.appendChild(card);
    });
  }

  // =========================================================================
  // SHARED ACTIONS
  // =========================================================================

  function startNew() {
    sessionStorage.removeItem('aip_s');
    rtc.stopCamera();
    rtc.cancelSpeech();
    proctor.stop();
    proctor.reset();
    S = _freshState();
    $('chatMessages').innerHTML = '';
    $('chatInput').value        = '';
    showPage('landing');
    backToModes();
  }
  window.startNew = startNew;

  function shareHRResult() {
    const fb = S.feedback;
    if (!fb) return;
    const t = `AI Placement Portal — HR Behavioral Interview\n${S.name}  ${S.jobTitle}\nCommunication: ${fb.communicationScore}/100\nCultural Fit: ${fb.culturalFitScore}/100\nConfidence: ${fb.confidenceScore}/100\nVerdict: ${fb.hiringVerdict}`;
    navigator.clipboard.writeText(t).then(() => showBanner('Copied to clipboard!', 'amber', 2000));
  }
  window.shareHRResult = shareHRResult;

  function shareMcqResult() {
    const qs      = S.mcq.questions;
    const correct = qs.filter(q => q.selected === q.correct).length;
    const pct     = Math.round((correct / qs.length) * 100);
    const t       = `AI Placement Portal — MCQ Assessment\nName: ${S.mcq.name}\nTopic: ${S.mcq.topic}\nScore: ${pct}%\nQuestions: ${qs.length}`;
    navigator.clipboard.writeText(t).then(() => showBanner('Copied to clipboard!', 'amber', 2000));
  }
  window.shareMcqResult = shareMcqResult;

  // Error overlay retry
  $('retryBtn').addEventListener('click', () => {
    $('errOvl').classList.add('hidden');
    if (S.phase === 'interview') {
      S.conv.pop();
      _getAssistantResponse();
    }
  });

  // =========================================================================
  // INIT
  // =========================================================================

  _loadSettingsUI();
  showPage('landing');

})();
