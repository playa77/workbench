/** Math Tutor Tab Component
 * Adaptive math tutor with SSE streaming, equation builder,
 * per-concept checkpoint MC questions, and comprehensive MC interviews.
 */

(function () {
  var activeSessionId = null;
  var activeReader = null;
  var activeAbortController = null;
  var currentMcq = null;
  var pendingConcept = null;
  var interviewStep = 0;
  var interviewData = {};

  var INTERVIEW_STEPS = [
    {
      id: 'type',
      question: "What kind of math are we working with?",
      render: function (ctx) {
        return '<select id="iw-type" style="width:100%;padding:10px 14px;font-size:14px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary)">'
          + '<option value="">— Select —</option>'
          + '<option value="ode">Ordinary Differential Equation</option>'
          + '<option value="pde">Partial Differential Equation</option>'
          + '<option value="integral">Integral</option>'
          + '<option value="derivative">Derivative</option>'
          + '<option value="series">Series / Sum</option>'
          + '<option value="limit">Limit</option>'
          + '<option value="algebraic">Algebraic Equation</option>'
          + '<option value="linear_algebra">Linear Algebra / Matrix</option>'
          + '<option value="probability">Probability / Statistics</option>'
          + '<option value="optimization">Optimization</option>'
          + '</select>';
      },
      getValue: function () { return document.getElementById('iw-type').value; },
      condition: null,
      label: 'Equation Type',
    },
    {
      id: 'order',
      question: "What's the order or highest derivative?",
      render: function (ctx) {
        return '<input type="number" id="iw-order" placeholder="e.g. 2 for second-order" style="width:100%;padding:10px 14px;font-size:14px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary)" min="0" />';
      },
      getValue: function () { return document.getElementById('iw-order').value; },
      condition: function (data) {
        return ['ode', 'pde', 'derivative'].indexOf(data.type) >= 0;
      },
      label: 'Order',
    },
    {
      id: 'nature',
      question: "What's the nature of the equation?",
      render: function (ctx) {
        var natures = ctx.type === 'ode' || ctx.type === 'pde'
          ? ['homogeneous', 'nonhomogeneous', 'linear', 'nonlinear', 'autonomous']
          : ['linear', 'nonlinear'];
        return '<select id="iw-nature" style="width:100%;padding:10px 14px;font-size:14px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary)">'
          + '<option value="">— Optional —</option>'
          + natures.map(function (n) {
            return '<option value="' + n + '">' + n.charAt(0).toUpperCase() + n.slice(1) + '</option>';
          }).join('')
          + '</select>';
      },
      getValue: function () { return document.getElementById('iw-nature').value; },
      condition: function (data) {
        return ['ode', 'pde', 'derivative', 'integral', 'algebraic', 'optimization'].indexOf(data.type) >= 0;
      },
      label: 'Nature',
    },
    {
      id: 'lhs',
      question: "Write the left-hand side of the equation.",
      render: function (ctx) {
        return '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">'
          + 'Use standard notation: y\'\' for second derivative, dy/dx, d^2y/dx^2, int(f(x))dx, sum_{n=0}^{\\infty}, etc.'
          + '</div>'
          + '<textarea id="iw-lhs" placeholder="e.g. d^2y/dx^2 + 3 dy/dx + 2y" style="width:100%;min-height:60px;padding:10px 14px;font-size:13px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary);font-family:var(--font-mono);resize:vertical"></textarea>';
      },
      getValue: function () { return document.getElementById('iw-lhs').value.trim(); },
      condition: null,
      label: 'Left Side',
    },
    {
      id: 'rhs',
      question: "What's on the right-hand side? (leave blank if zero)",
      render: function (ctx) {
        return '<textarea id="iw-rhs" placeholder="e.g. e^{-x} sin(2x) — or leave empty for = 0" style="width:100%;min-height:60px;padding:10px 14px;font-size:13px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary);font-family:var(--font-mono);resize:vertical"></textarea>';
      },
      getValue: function () { return document.getElementById('iw-rhs').value.trim(); },
      condition: function (data) {
        return ['ode', 'pde', 'derivative', 'integral', 'series', 'limit', 'algebraic', 'optimization'].indexOf(data.type) >= 0;
      },
      label: 'Right Side',
    },
    {
      id: 'variables',
      question: "What variables are involved?",
      render: function (ctx) {
        var hint = ctx.type === 'ode' ? 'e.g. x, y' : ctx.type === 'pde' ? 'e.g. x, y, t' : 'e.g. x, y, z';
        return '<input type="text" id="iw-variables" placeholder="' + hint + ' (comma-separated)" style="width:100%;padding:10px 14px;font-size:14px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary)" />';
      },
      getValue: function () { return document.getElementById('iw-variables').value.trim(); },
      condition: null,
      label: 'Variables',
    },
    {
      id: 'parameters',
      question: "Any constants or parameters?",
      render: function (ctx) {
        return '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">'
          + 'Enter as name=value pairs, e.g. m=2, k=0.5, g=9.81'
          + '</div>'
          + '<input type="text" id="iw-parameters" placeholder="e.g. m=2, k=0.5 (or leave blank)" style="width:100%;padding:10px 14px;font-size:14px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary)" />';
      },
      getValue: function () { return document.getElementById('iw-parameters').value.trim(); },
      condition: null,
      label: 'Parameters',
    },
    {
      id: 'conditions',
      question: "Are there any initial or boundary conditions?",
      render: function (ctx) {
        var hint = ctx.type === 'ode' ? 'e.g. y(0)=1, y\'(0)=0' : ctx.type === 'pde' ? 'e.g. u(x,0)=sin(πx), u(0,t)=0' : 'e.g. x(0)=0, lim_{t→∞} x(t)=0';
        return '<textarea id="iw-conditions" placeholder="' + hint + ' — or leave blank" style="width:100%;min-height:60px;padding:10px 14px;font-size:13px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary);font-family:var(--font-mono);resize:vertical"></textarea>';
      },
      getValue: function () { return document.getElementById('iw-conditions').value.trim(); },
      condition: null,
      label: 'Conditions',
    },
    {
      id: 'context',
      question: "What would you like the tutor to know about this equation? (optional)",
      render: function (ctx) {
        return '<textarea id="iw-context" placeholder="e.g. I want to understand how this models a damped harmonic oscillator..." style="width:100%;min-height:60px;padding:10px 14px;font-size:13px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-input);color:var(--text-primary);resize:vertical"></textarea>';
      },
      getValue: function () { return document.getElementById('iw-context').value.trim(); },
      condition: null,
      label: 'Context',
    },
  ];

  Router.register("math-tutor", renderMathTutorTab);

  function renderMathTutorTab(container) {
    cleanup();
    container.innerHTML = ''
      + '<div style="max-width:1100px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Math Tutor</h2>'
      +   '<div id="mt-phase-setup">'
      +     renderSetupPhase()
      +   '</div>'
      +   '<div id="mt-phase-chat" style="display:none"></div>'
      + '</div>';

    bindSetupEvents();
    checkExistingSession();
  }

  /* ---- Setup Phase ---- */

  function renderSetupPhase() {
    return ''
      + '<div class="card">'
      +   '<div class="card-header">Your Math Problem</div>'
      +   '<div class="form-group">'
      +     '<label>Describe your problem</label>'
      +     '<textarea class="mt-problem-input" id="mt-problem-text" placeholder="Describe your math problem in your own words. Include any equations (use $$ for LaTeX) — for example:\n\nSolve: $$\\frac{d^2x}{dt^2} + 3\\frac{dx}{dt} + 2x = 0$$\nwith initial conditions $$x(0) = 1, \\dot{x}(0) = 0$$\n\nOr describe a word problem: A tank contains 100 L of solution with 10 kg of salt..."></textarea>'
      +   '</div>'
      +   '<div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">'
      +     '<a href="#" id="mt-show-builder" style="color:var(--accent);text-decoration:none">^ Equation Builder (structured equation input)</a>'
      +   '</div>'
      +   '<div id="mt-eq-builder" style="display:none">'
      +     renderEquationBuilder()
      +   '</div>'
      +   '<div id="mt-build-preview" style="display:none;margin-top:12px">'
      +     '<label style="display:block;font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Built Equation (LaTeX)</label>'
      +     '<div class="mt-latex-preview" id="mt-latex-preview"></div>'
      +   '</div>'
      +   '<div style="margin-top:16px;display:flex;gap:8px">'
      +     '<button class="btn btn-primary" id="btn-mt-start">Start Tutor Session</button>'
      +     '<button class="btn btn-secondary" id="btn-mt-build" style="display:none">Build Equation</button>'
      +   '</div>'
      + '</div>';
  }

  function renderEquationBuilder() {
    return ''
      + '<div class="mt-eq-builder">'
      +   '<div style="font-size:13px;font-weight:600;margin-bottom:10px">Equation Builder</div>'
      +   '<div class="mt-eq-row">'
      +     '<select id="mt-eq-type" style="min-width:140px">'
      +       '<option value="">Select type...</option>'
      +       '<option value="ode">Ordinary Differential Equation</option>'
      +       '<option value="pde">Partial Differential Equation</option>'
      +       '<option value="integral">Integral</option>'
      +       '<option value="derivative">Derivative</option>'
      +       '<option value="series">Series / Sum</option>'
      +       '<option value="limit">Limit</option>'
      +       '<option value="algebraic">Algebraic Equation</option>'
      +       '<option value="linear_algebra">Linear Algebra / Matrix</option>'
      +       '<option value="probability">Probability / Statistics</option>'
      +       '<option value="optimization">Optimization</option>'
      +     '</select>'
      +     '<input type="number" id="mt-eq-order" placeholder="Order (e.g. 2)" style="width:90px" min="0" />'
      +     '<select id="mt-eq-nature" style="min-width:120px">'
      +       '<option value="">Nature...</option>'
      +       '<option value="homogeneous">Homogeneous</option>'
      +       '<option value="nonhomogeneous">Non-homogeneous</option>'
      +       '<option value="linear">Linear</option>'
      +       '<option value="nonlinear">Non-linear</option>'
      +       '<option value="autonomous">Autonomous</option>'
      +     '</select>'
      +   '</div>'
      +   '<div class="mt-eq-row">'
      +     '<input type="text" id="mt-eq-lhs" placeholder="Left-hand side (e.g. dy/dx + 2xy)" style="flex:1" />'
      +     '<span style="font-size:13px;color:var(--text-primary);padding:6px 0">=</span>'
      +     '<input type="text" id="mt-eq-rhs" placeholder="Right-hand side (e.g. e^{-x^2})" style="flex:1" />'
      +   '</div>'
      +   '<div class="mt-eq-row">'
      +     '<input type="text" id="mt-eq-vars" placeholder="Variables (comma-separated, e.g. x,y)" style="flex:1" />'
      +     '<input type="text" id="mt-eq-params" placeholder="Parameters (e.g. m=2,k=5)" style="flex:1" />'
      +   '</div>'
      +   '<div class="mt-eq-row">'
      +     '<input type="text" id="mt-eq-conds" placeholder="Initial/boundary conditions (e.g. x(0)=1, dx/dt(0)=0)" style="width:100%" />'
      +   '</div>'
      +   '<div style="font-size:11px;color:var(--text-muted);margin-top:4px">'
      +     'Tip: Use standard notation. y\'\' means second derivative, int(...)dx for integrals.'
      +   '</div>'
      + '</div>';
  }

  function bindSetupEvents() {
    var showBuilder = document.getElementById('mt-show-builder');
    if (showBuilder) {
      showBuilder.addEventListener('click', function (e) {
        e.preventDefault();
        var el = document.getElementById('mt-eq-builder');
        var btn = document.getElementById('btn-mt-build');
        var expanded = el.style.display !== 'none';
        el.style.display = expanded ? 'none' : 'block';
        btn.style.display = expanded ? 'none' : 'inline-block';
        showBuilder.textContent = expanded ? '^ Equation Builder (structured equation input)' : 'v Hide Equation Builder';
      });
    }

    var btnBuild = document.getElementById('btn-mt-build');
    if (btnBuild) {
      btnBuild.addEventListener('click', buildEquation);
    }

    var btnStart = document.getElementById('btn-mt-start');
    if (btnStart) {
      btnStart.addEventListener('click', startSession);
    }
  }

  function buildEquation() {
    var eqType = document.getElementById('mt-eq-type').value;
    var lhs = document.getElementById('mt-eq-lhs').value.trim();
    var rhs = document.getElementById('mt-eq-rhs').value.trim();
    var vars = document.getElementById('mt-eq-vars').value.trim();
    var params = document.getElementById('mt-eq-params').value.trim();
    var conds = document.getElementById('mt-eq-conds').value.trim();
    var order = document.getElementById('mt-eq-order').value;
    var nature = document.getElementById('mt-eq-nature').value;

    if (!eqType || (!lhs)) {
      Utils.showToast('Select an equation type and fill in at minimum the left-hand side.', 'error');
      return;
    }

    var varList = vars ? vars.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
    var paramMap = {};
    if (params) {
      params.split(',').forEach(function (p) {
        var kv = p.trim().split('=');
        if (kv.length === 2) paramMap[kv[0].trim()] = kv[1].trim();
      });
    }

    window._mtEquationJson = {
      type: eqType,
      order: order ? parseInt(order) : null,
      nature: nature || null,
      lhs: lhs,
      rhs: rhs || null,
      variables: varList,
      parameters: paramMap,
      conditions: conds || null,
    };

    var latex = buildLatex(window._mtEquationJson);
    window._mtEquationLatex = latex;

    var preview = document.getElementById('mt-build-preview');
    var latexPreview = document.getElementById('mt-latex-preview');
    if (preview && latexPreview) {
      preview.style.display = 'block';
      latexPreview.innerHTML = Utils.escapeHtml(latex);
    }
  }

  function buildLatex(eq) {
    var parts = [];
    var latex = eq.lhs || '';
    if (eq.rhs) latex += ' = ' + eq.rhs;
    parts.push('$$' + latex + '$$');
    if (eq.type) parts.push('\\\\text{Type: } ' + eq.type.replace(/_/g, '\\_'));
    if (eq.order) parts.push('\\\\text{Order: }' + eq.order);
    if (eq.nature) parts.push('\\\\text{Nature: } ' + eq.nature.replace(/_/g, '\\_'));
    if (eq.variables && eq.variables.length) parts.push('\\\\text{Variables: }' + eq.variables.join(', '));
    if (eq.conditions) parts.push('\\\\text{Conditions: }' + eq.conditions);
    return parts.join(' \\\\\\\\ ');
  }

  async function startSession() {
    var btn = document.getElementById('btn-mt-start');
    Utils.setButtonLoading(btn, 'Starting...');
    var problemText = document.getElementById('mt-problem-text').value.trim();
    if (!problemText) { Utils.showToast('Describe your problem first.', 'error'); Utils.resetButton(btn); return; }

    document.getElementById('mt-phase-setup').style.display = 'none';

    try {
      var body = { problem: problemText };
      if (window._mtEquationJson) body.equation_json = window._mtEquationJson;
      if (window._mtEquationLatex) body.equation_latex = window._mtEquationLatex;

      var resp = await fetch('/api/v1/agents/math-tutor/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        Utils.showToast('Error: ' + (err.detail || resp.statusText), 'error');
        document.getElementById('mt-phase-setup').style.display = 'block';
        Utils.resetButton(btn);
        return;
      }

      renderChatPhase(body);
      streamResponse(resp);
    } catch (e) {
      Utils.showToast('Failed to start: ' + e.message, 'error');
      document.getElementById('mt-phase-setup').style.display = 'block';
      Utils.resetButton(btn);
    }
  }

  /* ---- Chat Phase ---- */

  function renderChatPhase(startBody) {
    var chatArea = document.getElementById('mt-phase-chat');
    chatArea.style.display = 'block';
    chatArea.innerHTML = ''
      + '<div class="mt-chat-layout">'
      +   '<div class="mt-chat-left">'
      +     '<div class="mt-problem-card">'
      +       '<h4>Problem</h4>'
      +       '<div class="mt-problem-text">' + Utils.escapeHtml(startBody.problem) + '</div>'
      +       + (window._mtEquationLatex ? '<div class="mt-latex-display">' + Utils.escapeHtml(window._mtEquationLatex) + '</div>' : '')
      +     '</div>'
      +     '<div class="card" style="padding:12px">'
      +       '<h4>Status</h4>'
      +       '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
      +         '<span style="font-size:12px;color:var(--text-muted)">Level:</span>'
      +         '<span class="mt-competency-badge" id="mt-competency">—</span>'
      +       '</div>'
      +       '<div style="display:flex;align-items:center;gap:8px">'
      +         '<span style="font-size:12px;color:var(--text-muted)">Assessment:</span>'
      +         '<span style="font-size:12px" id="mt-assessment-mode">—</span>'
      +       '</div>'
      +     '</div>'
      +     '<div class="card" style="padding:12px">'
      +       '<h4>Concepts</h4>'
      +       '<ul class="mt-concept-list" id="mt-concepts"><li style="font-size:12px;color:var(--text-muted)">Waiting...</li></ul>'
      +     '</div>'
      +     '<div style="display:flex;flex-direction:column;gap:6px">'
      +       '<button class="btn btn-secondary btn-sm" id="btn-mt-build-eq">+ Build Equation</button>'
      +       '<button class="btn btn-secondary btn-sm" id="btn-mt-interview">Comprehensive MC Interview</button>'
      +       '<button class="btn btn-danger btn-sm" id="btn-mt-end" style="margin-top:4px">End Session</button>'
      +     '</div>'
      +   '</div>'
      +   '<div class="mt-chat-right">'
      +     '<div class="mt-chat-messages" id="mt-chat-messages">'
      +       '<div style="text-align:center;color:var(--text-muted);padding:40px">'
      +         '<div class="spinner" style="width:16px;height:16px;margin-bottom:8px"></div>'
      +         'Tutor is thinking...'
      +       '</div>'
      +     '</div>'
      +     '<div id="mt-mcq-area"></div>'
      +     '<div class="mt-chat-input-row">'
      +       '<input class="form-input" id="mt-chat-input" placeholder="Ask a question or discuss a step..." onkeydown="if(event.key===\'Enter\')window._mtSendMessage()" />'
      +       '<button class="btn btn-primary" id="btn-mt-send">Send</button>'
      +     '</div>'
      +   '</div>'
      + '</div>';

    document.getElementById('mt-chat-messages').innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:40px"><div class="spinner" style="width:16px;height:16px;margin-bottom:8px"></div>Tutor is thinking...</div>';

    document.getElementById('btn-mt-end').addEventListener('click', endSession);
    document.getElementById('btn-mt-build-eq').addEventListener('click', openEquationInterview);
    document.getElementById('btn-mt-interview').addEventListener('click', function () { requestAssessment('entire problem'); });
    document.getElementById('btn-mt-send').addEventListener('click', sendMessage);
  }

  /* ---- SSE Streaming ---- */

  function streamResponse(resp) {
    if (activeReader) { activeReader.cancel(); activeReader = null; }
    activeAbortController = new AbortController();

    var messages = document.getElementById('mt-chat-messages');
    if (messages) messages.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:40px"><div class="spinner" style="width:16px;height:16px;margin-bottom:8px"></div>Tutor is thinking...</div>';

    var reader = resp.body.getReader();
    activeReader = reader;
    var decoder = new TextDecoder();
    var buffer = '';
    var currentMsg = null;

    function process() {
      reader.read().then(function (result) {
        if (result.done) { return; }

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line) continue;

          if (line.startsWith('event: ')) {
            var eventType = line.slice(7);
            var nextLine = lines[i + 1];
            var data = {};
            if (nextLine && nextLine.startsWith('data: ')) {
              try { data = JSON.parse(nextLine.slice(6)); } catch (e) {}
              i++;
            }

            handleSSEEvent(eventType, data);
          }
        }

        process();
      }).catch(function (e) {
        if (e.name !== 'AbortError' && e.message.indexOf('reader') < 0) {
          addSystemMessage('Connection error: ' + Utils.escapeHtml(e.message));
        }
      });
    }

    process();
  }

  function handleSSEEvent(eventType, data) {
    if (eventType === 'session_id') {
      activeSessionId = data.session_id;
    } else if (eventType === 'chunk') {
      appendStreamChunk(data.content);
    } else if (eventType === 'done') {
      finalizeMessage();
    } else if (eventType === 'error') {
      addSystemMessage('Error: ' + Utils.escapeHtml(data.message || 'Unknown'));
    } else if (eventType === 'checkpoint_prompt') {
      pendingConcept = data.concept;
      addConceptPrompt(data.concept, data.message);
    } else if (eventType === 'mcq') {
      renderMcq(data);
    }
  }

  function appendStreamChunk(content) {
    var messages = document.getElementById('mt-chat-messages');
    if (!content) return;

    if (messages.querySelector('div[style*="text-align:center"]')) {
      messages.innerHTML = '';
    }

    var lastMsg = messages.querySelector('.mt-chat-msg.tutor.streaming');
    if (!lastMsg) {
      lastMsg = document.createElement('div');
      lastMsg.className = 'mt-chat-msg tutor streaming';
      lastMsg.innerHTML = '<div class="mt-chat-sender">Tutor</div><div class="mt-chat-body"></div>';
      messages.appendChild(lastMsg);
    }

    var body = lastMsg.querySelector('.mt-chat-body');
    body.textContent += content;
    body.innerHTML = renderMessageContent(body.textContent);
    messages.scrollTop = messages.scrollHeight;
  }

  function finalizeMessage() {
    var messages = document.getElementById('mt-chat-messages');
    var streaming = messages && messages.querySelector('.mt-chat-msg.streaming');
    if (streaming) streaming.classList.remove('streaming');
  }

  function addSystemMessage(content) {
    var messages = document.getElementById('mt-chat-messages');
    if (!messages) return;
    var div = document.createElement('div');
    div.className = 'mt-chat-msg system';
    div.innerHTML = content;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function addStudentMessage(content) {
    var messages = document.getElementById('mt-chat-messages');
    if (!messages) return;
    var div = document.createElement('div');
    div.className = 'mt-chat-msg student';
    div.innerHTML = '<div class="mt-chat-sender">You</div>' + renderMessageContent(content);
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function renderMessageContent(text) {
    var escaped = Utils.escapeHtml(text);
    escaped = escaped.replace(/\\$\\$([^$]+)\\$\\$/g, '<div class="mt-latex-display" style="margin:8px 0">$1</div>');
    escaped = escaped.replace(/\\$([^$]+)\\$/g, '<code style="font-size:12px">$1</code>');
    escaped = escaped.replace(/\n\n/g, '</div><div class="mt-chat-body" style="margin-top:8px">');
    return escaped;
  }

  function addConceptPrompt(concept, message) {
    var messages = document.getElementById('mt-chat-messages');
    if (!messages) return;
    var div = document.createElement('div');
    div.className = 'mt-prompt-box';
    div.innerHTML = ''
      + Utils.escapeHtml(message)
      + '<div style="margin-top:8px;display:flex;gap:6px">'
      +   '<button class="btn btn-primary btn-sm" data-concept="' + Utils.escapeHtml(concept) + '" onclick="window._mtConceptCheckpoint(this.dataset.concept)">Take Checkpoint</button>'
      +   '<button class="btn btn-secondary btn-sm" data-concept="' + Utils.escapeHtml(concept) + '" onclick="window._mtSkipCheckpoint(this.dataset.concept)">Skip</button>'
      + '</div>';
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  /* ---- Messaging ---- */

  window._mtSendMessage = sendMessage;

  async function sendMessage() {
    var btn = document.getElementById('btn-mt-send');
    Utils.setButtonLoading(btn, 'Sending...');
    var input = document.getElementById('mt-chat-input');
    if (!input) { Utils.resetButton(btn); return; }
    var msg = input.value.trim();
    if (!msg || !activeSessionId) { Utils.resetButton(btn); return; }
    input.value = '';
    addStudentMessage(msg);

    try {
      var resp = await fetch('/api/v1/agents/math-tutor/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSessionId, message: msg }),
      });

      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        addSystemMessage('Error: ' + Utils.escapeHtml(err.detail || resp.statusText));
        Utils.resetButton(btn);
        return;
      }

      streamResponse(resp);
    } catch (e) {
      addSystemMessage('Failed to send: ' + Utils.escapeHtml(e.message));
    }
    Utils.resetButton(btn);
  }

  /* ---- Concept Checkpoints ---- */

  window._mtConceptCheckpoint = function (concept) {
    pendingConcept = null;
    requestAssessment(concept);
  };

  window._mtSkipCheckpoint = function (concept) {
    addSystemMessage('Checkpoint for "' + Utils.escapeHtml(concept) + '" skipped.');
    var box = document.querySelector('.mt-prompt-box');
    if (box) box.style.display = 'none';
    if (concept) addConceptTag(concept);
    pendingConcept = null;
  };

  /* ---- Assessment ---- */

  async function requestAssessment(scope) {
    try {
      var resp = await fetch('/api/v1/agents/math-tutor/assess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSessionId, scope: scope }),
      });
      var mcq = await resp.json();
      if (mcq.error) {
        addSystemMessage('Could not generate assessment: ' + Utils.escapeHtml(mcq.error));
        return;
      }
      renderMcq(mcq);
    } catch (e) {
      addSystemMessage('Assessment error: ' + Utils.escapeHtml(e.message));
    }
  }

  function renderMcq(mcq) {
    currentMcq = mcq;
    var area = document.getElementById('mt-mcq-area');
    if (!area) return;
    area.innerHTML = ''
      + '<div class="mt-mcq-card" id="mt-mcq">'
      +   '<h5>' + (Utils.escapeHtml(mcq.question) || 'Multiple Choice Question') + '</h5>'
      +   (Object.keys(mcq.options || {}).map(function (key) {
          return '<div class="mt-mcq-option" data-option="' + Utils.escapeHtml(key) + '" onclick="window._mtSelectOption(this)">'
            + '<div class="mt-mcq-radio"></div>'
            + '<span>' + Utils.escapeHtml(key) + '. ' + Utils.escapeHtml(mcq.options[key]) + '</span>'
            + '</div>';
        }).join(''))
      +   '<div style="margin-top:12px;display:flex;gap:8px;align-items:center">'
      +     '<button class="btn btn-primary btn-sm" id="btn-mt-submit-answer" onclick="window._mtSubmitAnswer()">Submit Answer</button>'
      +     '<span id="mt-answer-feedback" style="font-size:12px"></span>'
      +   '</div>'
      + '</div>';
  }

  window._mtSelectOption = function (el) {
    if (el.classList.contains('disabled')) return;
    var all = document.querySelectorAll('.mt-mcq-option');
    all.forEach(function (o) { o.classList.remove('selected'); });
    el.classList.add('selected');
  };

  window._mtSubmitAnswer = async function () {
    if (!currentMcq) return;
    var selected = document.querySelector('.mt-mcq-option.selected');
    if (!selected) { Utils.showToast('Select an answer first.', 'error'); return; }
    var answer = selected.dataset.option;

    var all = document.querySelectorAll('.mt-mcq-option');
    all.forEach(function (o) { o.classList.add('disabled'); });

    if (answer === currentMcq.correct) {
      selected.classList.add('correct');
      addSystemMessage('Correct! ' + (currentMcq.explanation ? Utils.escapeHtml(currentMcq.explanation) : ''));
    } else {
      selected.classList.add('wrong');
      all.forEach(function (o) {
        if (o.dataset.option === currentMcq.correct) o.classList.add('correct');
      });
    }

    try {
      var resp = await fetch('/api/v1/agents/math-tutor/assess/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: activeSessionId,
          question: currentMcq.question,
          options: currentMcq.options,
          answer: answer,
        }),
      });
      var result = await resp.json();
      if (result.feedback) {
        addSystemMessage(result.feedback.replace(/COMPETENCY:.*/, ''));
      }
      if (result.competency_level) {
        document.getElementById('mt-competency').textContent = competencyLabel(result.competency_level);
      }
    } catch (e) { /* silent */ }

    currentMcq = null;
    document.getElementById('mt-mcq-area').innerHTML = '';
  };

  /* ---- Interview-style Equation Wizard ---- */

  function getActiveInterviewSteps() {
    return INTERVIEW_STEPS.filter(function (step) {
      if (!step.condition) return true;
      return step.condition(interviewData);
    });
  }

  function openEquationInterview() {
    interviewStep = 0;
    interviewData = {};
    renderInterviewOverlay();
    var overlay = document.getElementById('mt-interview-overlay');
    if (overlay) overlay.style.display = 'flex';
  }

  function closeInterview() {
    var overlay = document.getElementById('mt-interview-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  function renderInterviewOverlay() {
    var existing = document.getElementById('mt-interview-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.id = 'mt-interview-overlay';
    overlay.className = 'mt-interview-overlay';
    overlay.innerHTML = ''
      + '<div class="mt-interview-dialog">'
      +   '<div class="mt-interview-header">'
      +     '<span>Equation Builder</span>'
      +     '<button class="btn-icon" id="btn-iw-close" style="width:28px;height:28px">&times;</button>'
      +   '</div>'
      +   '<div class="mt-interview-progress" id="iw-progress"></div>'
      +   '<div class="mt-interview-body" id="iw-body">'
      +     '<h3 class="mt-interview-question" id="iw-question"></h3>'
      +     '<div id="iw-input-area"></div>'
      +   '</div>'
      +   '<div class="mt-interview-preview" id="iw-preview" style="display:none">'
      +     '<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Assembled Equation</div>'
      +     '<div class="mt-latex-preview" id="iw-latex-preview" style="margin-bottom:10px"></div>'
      +     '<div style="font-size:10px;font-weight:600;color:var(--text-muted);margin-bottom:4px">JSON Structure</div>'
      +     '<pre id="iw-json-preview" style="font-size:10px;max-height:120px;overflow-y:auto;margin-bottom:0"></pre>'
      +     '<div class="mt-interview-summary" id="iw-summary"></div>'
      +   '</div>'
      +   '<div class="mt-interview-footer" id="iw-footer">'
      +     '<button class="btn btn-secondary btn-sm" id="btn-iw-back" style="display:none">^ Back</button>'
      +     '<div style="flex:1"></div>'
      +     '<button class="btn btn-secondary btn-sm" id="btn-iw-skip" style="display:none">Skip</button>'
      +     '<button class="btn btn-primary btn-sm" id="btn-iw-next">Next v</button>'
      +     '<button class="btn btn-primary btn-sm" id="btn-iw-finish" style="display:none">Send to Tutor</button>'
      +   '</div>'
      + '</div>';

    document.body.appendChild(overlay);

    document.getElementById('btn-iw-close').addEventListener('click', closeInterview);
    document.getElementById('btn-iw-next').addEventListener('click', advanceInterviewStep);
    document.getElementById('btn-iw-back').addEventListener('click', goBackInterviewStep);
    document.getElementById('btn-iw-skip').addEventListener('click', skipInterviewStep);
    document.getElementById('btn-iw-finish').addEventListener('click', finishInterview);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeInterview();
    });

    renderInterviewStep(0);
  }

  function renderInterviewStep(idx) {
    var activeSteps = getActiveInterviewSteps();
    var total = activeSteps.length;
    var step = activeSteps[idx];

    document.getElementById('iw-question').textContent = step.question;
    document.getElementById('iw-input-area').innerHTML = step.render(interviewData);

    var progress = document.getElementById('iw-progress');
    var dots = '';
    for (var i = 0; i < total; i++) {
      var cls = i === idx ? 'active' : i < idx ? 'done' : '';
      dots += '<span class="mt-interview-dot ' + cls + '" title="' + Utils.escapeHtml(activeSteps[i].label) + '"></span>';
    }
    progress.innerHTML = ''
      + '<span style="font-size:11px;color:var(--text-muted)">Step ' + (idx + 1) + ' of ' + total + '</span>'
      + '<div style="display:flex;gap:6px;margin-top:6px">' + dots + '</div>';

    var isLast = idx >= total - 1;
    document.getElementById('btn-iw-back').style.display = idx > 0 ? 'inline-flex' : 'none';
    document.getElementById('btn-iw-skip').style.display = (step.id !== 'lhs' && !isLast) ? 'inline-flex' : 'none';
    document.getElementById('btn-iw-next').style.display = isLast ? 'none' : 'inline-flex';
    document.getElementById('btn-iw-finish').style.display = isLast ? 'inline-flex' : 'none';

    var preview = document.getElementById('iw-preview');
    if (isLast) preview.style.display = 'block';
  }

  function collectStepValue() {
    var activeSteps = getActiveInterviewSteps();
    var step = activeSteps[interviewStep];
    var val = step.getValue();
    if (val) interviewData[step.id] = val;
  }

  function advanceInterviewStep() {
    var activeSteps = getActiveInterviewSteps();
    var step = activeSteps[interviewStep];

    if (step.id === 'lhs') {
      var val = step.getValue();
      if (!val) { Utils.showToast('The left-hand side is required.', 'error'); return; }
      interviewData.lhs = val;
    } else if (step.id === 'type') {
      var val = step.getValue();
      if (!val) { Utils.showToast('Please select an equation type.', 'error'); return; }
      interviewData = { type: val };
    } else {
      collectStepValue();
    }

    interviewStep++;
    if (interviewStep >= getActiveInterviewSteps().length) interviewStep = getActiveInterviewSteps().length - 1;

    if (interviewStep === getActiveInterviewSteps().length - 1) {
      buildInterviewPreview();
    }

    renderInterviewStep(interviewStep);

    var focusEl = document.getElementById('iw-question');
    if (focusEl) focusEl.scrollIntoView({ behavior: 'smooth' });
  }

  function goBackInterviewStep() {
    if (interviewStep > 0) interviewStep--;
    renderInterviewStep(interviewStep);
  }

  function skipInterviewStep() {
    interviewStep++;
    if (interviewStep >= getActiveInterviewSteps().length) interviewStep = getActiveInterviewSteps().length - 1;

    if (interviewStep === getActiveInterviewSteps().length - 1) {
      buildInterviewPreview();
    }

    renderInterviewStep(interviewStep);
  }

  function buildInterviewPreview() {
    var activeSteps = getActiveInterviewSteps();
    var lastStep = activeSteps[activeSteps.length - 1];
    if (lastStep.id === 'context') {
      var contextEl = document.getElementById('iw-context');
      if (contextEl) interviewData.context = contextEl.value.trim();
    }

    var eqJson = {
      type: interviewData.type || '',
      order: interviewData.order ? parseInt(interviewData.order) : null,
      nature: interviewData.nature || null,
      lhs: interviewData.lhs || '',
      rhs: interviewData.rhs || null,
      variables: interviewData.variables
        ? interviewData.variables.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [],
      parameters: {},
      conditions: interviewData.conditions || null,
    };

    if (interviewData.parameters) {
      interviewData.parameters.split(',').forEach(function (p) {
        var kv = p.trim().split('=');
        if (kv.length === 2) eqJson.parameters[kv[0].trim()] = kv[1].trim();
      });
    }

    window._iwEquationJson = eqJson;
    window._iwEquationLatex = buildLatex(eqJson);

    document.getElementById('iw-latex-preview').innerHTML = Utils.escapeHtml(window._iwEquationLatex);
    document.getElementById('iw-json-preview').textContent = JSON.stringify(eqJson, null, 2);

    var summary = document.getElementById('iw-summary');
    summary.innerHTML = '';
    activeSteps.filter(function (s) { return s.id !== 'context'; }).forEach(function (s) {
      var val = interviewData[s.id];
      if (val) {
        summary.innerHTML += '<div style="font-size:11px;margin-bottom:4px"><strong>' + Utils.escapeHtml(s.label) + ':</strong> ' + Utils.escapeHtml(String(val)) + '</div>';
      }
    });
  }

  async function finishInterview() {
    var btn = document.getElementById('btn-iw-finish');
    Utils.setButtonLoading(btn, 'Sending...');
    var activeSteps = getActiveInterviewSteps();
    var lastStep = activeSteps[activeSteps.length - 1];
    if (lastStep.id === 'context') {
      var contextEl = document.getElementById('iw-context');
      if (contextEl) interviewData.context = contextEl.value.trim();
    }

    buildInterviewPreview();
    closeInterview();

    if (!window._iwEquationJson || !window._iwEquationLatex) { Utils.resetButton(btn); return; }

    addStudentMessage('Added equation:\n$$' + window._iwEquationLatex + '$$');

    try {
      var body = {
        session_id: activeSessionId,
        equation_json: window._iwEquationJson,
        equation_latex: window._iwEquationLatex,
        context: interviewData.context || '',
      };

      var resp = await fetch('/api/v1/agents/math-tutor/equation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        addSystemMessage('Error: ' + Utils.escapeHtml(err.detail || resp.statusText));
        Utils.resetButton(btn);
        return;
      }

      streamResponse(resp);
    } catch (e) {
      addSystemMessage('Failed to send equation: ' + Utils.escapeHtml(e.message));
    }
    Utils.resetButton(btn);
  }

  /* ---- Deep Dive ---- */

  window._mtDeepDive = async function (topic, context) {
    try {
      var resp = await fetch('/api/v1/agents/math-tutor/deep-dive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSessionId, topic: topic, context: context }),
      });
      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        addSystemMessage('Deep dive error: ' + Utils.escapeHtml(err.detail || resp.statusText));
        return;
      }
      addStudentMessage('Deep dive into: ' + topic);
      streamResponse(resp);
    } catch (e) {
      addSystemMessage('Deep dive failed: ' + Utils.escapeHtml(e.message));
    }
  };

  /* ---- Session ---- */

  function addConceptTag(concept) {
    var list = document.getElementById('mt-concepts');
    if (!list) return;
    if (list.querySelector('li[style*="text-align"]')) list.innerHTML = '';
    var li = document.createElement('li');
    li.className = 'mt-concept-item';
    li.innerHTML = '<span>' + Utils.escapeHtml(concept) + '</span>'
      + '<a href="#" style="font-size:10px;color:var(--accent);text-decoration:none" onclick="window._mtDeepDive(\''
      + Utils.escapeHtml(concept).replace(/'/g, "\\'") + '\',\'\');return false">Deep Dive</a>';
    list.appendChild(li);
  }

  async function checkExistingSession() {
    try {
      var resp = await fetch('/api/v1/agents/math-tutor/session');
      var data = await resp.json();
      if (data.session_id) {
        activeSessionId = data.session_id;
        document.getElementById('mt-competency').textContent = competencyLabel(data.competency_level);
        document.getElementById('mt-assessment-mode').textContent = data.assessment_mode;
        document.getElementById('mt-phase-setup').style.display = 'none';

        renderChatPhase({ problem: data.problem });

        if (window._mtEquationLatex) {
          var latexEl = document.querySelector('.mt-latex-display');
          if (latexEl) latexEl.innerHTML = Utils.escapeHtml(window._mtEquationLatex);
        }

        var messages = document.getElementById('mt-chat-messages');
        messages.innerHTML = '';
        data.chat_history.forEach(function (entry) {
          if (entry.role === 'user') {
            addStudentMessage(entry.content);
          } else if (entry.role === 'assistant') {
            var div = document.createElement('div');
            div.className = 'mt-chat-msg tutor';
            div.innerHTML = '<div class="mt-chat-sender">Tutor</div>' + renderMessageContent(entry.content);
            messages.appendChild(div);
          } else if (entry.role === 'system') {
            addSystemMessage(entry.content);
          }
        });
        messages.scrollTop = messages.scrollHeight;

        data.concepts_covered.forEach(function (c) { addConceptTag(c); });
      }
    } catch (e) { /* no active session */ }
  }

  async function endSession() {
    var btn = document.getElementById('btn-mt-end');
    Utils.setButtonLoading(btn, 'Ending...');
    try {
      await fetch('/api/v1/agents/math-tutor/session', { method: 'DELETE' });
    } catch (e) { /* silent */ }
    cleanup();
    activeSessionId = null;
    var container = document.getElementById('active-tab-content');
    if (container) renderMathTutorTab(container);
  }

  function cleanup() {
    if (activeReader) {
      try { activeReader.cancel(); } catch (e) { /* silent */ }
      activeReader = null;
    }
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }
  }

  function competencyLabel(level) {
    var labels = {
      'smart_high_school': 'Smart HS Senior',
      'college_freshman': 'College Freshman',
      'college_senior': 'College Senior',
      'grad_student': 'Grad Student',
    };
    return labels[level] || level;
  }
})();
