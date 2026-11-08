if (typeof window !== 'undefined') {
const pause = () => new Promise(resolve => setTimeout(resolve, 20));
async function until(fn) {
  for(let i=0;i<1000;i++){ if(fn()) return; await pause(); }
  throw Error('DOM wait timed out');
}
const assert = (value, reason) => { if(!value) throw Error(reason); };
const $ = selector => document.querySelector(selector);
function contrast(a, b) {
  const luminance = color => {
    const c = color.match(/[\d.]+/g).slice(0,3).map(n => {
      const v=Number(n)/255; return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;
    });
    return c[0]*.2126+c[1]*.7152+c[2]*.0722;
  };
  const x=luminance(a), y=luminance(b);
  return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
}
function styles() {
  assert(getComputedStyle(document.body).margin === '0px', 'CSS reset missing');
  assert(getComputedStyle(document.body).fontFamily.includes('Segoe UI'), 'Typography missing');
  assert(getComputedStyle($('.workspace')).display === 'grid', 'Layout missing');
  assert(getComputedStyle($('.primary')).backgroundColor === 'rgb(36, 88, 184)', 'Button CSS missing');
  assert(document.documentElement.scrollWidth <= innerWidth, 'Horizontal overflow');
  const box = $('#submit').getBoundingClientRect();
  assert(box.top >= 0 && box.bottom <= innerHeight, 'Composer send button is not visible');
  for(const node of [$('#submit'), ...document.querySelectorAll('.badge')]) {
    const css=getComputedStyle(node);
    assert(contrast(css.color,css.backgroundColor)>=4.5, 'Text contrast is insufficient');
  }
}
try {
  await until(() => document.body.dataset.chatReady === 'true');
  styles();
  for(const control of document.querySelectorAll('input,select,textarea'))
    assert(control.labels?.length, 'Unlabeled control ' + control.id);
  if(sessionStorage.getItem('reload-check')) {
    await until(() => document.querySelectorAll('.turn-result .evidence-toggle').length === 9);
    assert((await (await fetch('/__stats')).json()).posts === 9, 'Refresh repeated POST');
    assert(document.querySelectorAll('.user-message').length === 9, 'Conversation lost on refresh');
    const evidence = $('.evidence-toggle'); evidence.open = true;
    assert(evidence.textContent.includes('Vehicles build up'), 'Saved evidence missing');
    $('#new-chat').click();
    assert(!document.querySelector('.turn') && !$('#welcome').hidden, 'New chat did not clear messages');
    $('#question').value='New constraint question'; $('#question-form').requestSubmit();
    await until(() => !$('#submit').disabled && $('.evidence-toggle'));
    const stats=await (await fetch('/__stats')).json();
    assert(stats.posts===10 && !stats.requests[9].previous_investigation_id, 'New chat reused context');
    assert(document.querySelectorAll('.user-message').length===1, 'Old messages leaked into new chat');
    styles(); document.body.dataset.browserResult = 'passed';
  } else {
    assert(!$('#welcome').hidden, 'Empty chat missing');
    $('#examples button').click();
    assert($('#question').value.length > 3, 'Example selection failed');
    const cases=['Constraint','Segments','Causes','What-if','Combined','clarification_required','unsupported','incomplete','failed'];
    for (const name of cases) {
      if(name==='failed') {
        $('#end').value='2026-09-15T00:00:00'; $('#end').dispatchEvent(new Event('change'));
      }
      $('#question').value=name; $('#question-form').requestSubmit();
      await until(() => $('.turn:last-child .turn-progress [data-status="active"]'));
      assert($('#new-chat').disabled, 'Active execution can be cleared');
      await until(() => !$('#submit').disabled && $('.turn:last-child .evidence-toggle'));
      const root=$('.turn:last-child .turn-result'), outcome=cases.indexOf(name)<5?'completed':name;
      assert(root.querySelector('[data-status="'+outcome+'"]'), 'Outcome missing');
      const details=root.querySelector('.evidence-toggle');
      assert(!details.open, 'Evidence should start collapsed');
      if(name==='Segments') {
        const comparison=root.querySelector('.answer > .answer-comparison');
        assert(comparison && comparison.getBoundingClientRect().height>0, 'Comparison hidden');
        assert(comparison.textContent.includes('SUV') && comparison.textContent.includes('Sedan') &&
          comparison.textContent.includes('Framing'), 'Model candidates absent from main answer');
        assert(!details.contains(comparison), 'Comparison is only under evidence');
      }
      details.open=true;
      if(['Constraint','Combined'].includes(name))
        assert(details.querySelector('[data-value="46.88"]'), 'Historical value changed');
      if(['What-if','Combined'].includes(name)) {
        assert(details.querySelector('[data-value="46.255889"]'), 'Simulation value changed');
        assert(details.textContent.includes('95% confidence interval'), 'Uncertainty missing');
      }
      assert(!root.querySelector('img')&&!window.injected&&!root.querySelector('pre'), 'Unsafe/raw rendering');
      if(['Causes','Combined'].includes(name)) {
        const source=details.querySelector('.evidence-item');
        assert(source.textContent.includes('Maintenance work order'), 'Readable source heading missing');
        assert(source.textContent.includes('link is inferred'), 'Inferred link qualification missing');
        const more=[...source.querySelectorAll('button')].find(b=>b.textContent==='Read full passage');
        assert(more, 'Shortened excerpt should offer the full passage');
        more.click(); assert(source.querySelector('blockquote').textContent.length>400, 'Full source unavailable');
      }
      for(const internal of ['Historical measurement provenance','Saved workflow checkpoints',
          'Aggregate source references','Executive summary','No simulation result was returned'])
        assert(!details.textContent.includes(internal), 'Internal evidence dump returned: '+internal);
      if(name==='Constraint') {
        assert(details.textContent.includes('Vehicles build up'), 'Plain supporting evidence absent');
        assert(!details.textContent.includes('0.9998'), 'Normalized score exposed as evidence');
        assert(details.textContent.split(/\s+/).length<240, 'Constraint evidence is too long');
      }
      styles();
    }
    const stats=await (await fetch('/__stats')).json();
    assert(stats.requests[1].previous_investigation_id, 'Follow-up parent absent');
    assert(!stats.requests[0].previous_investigation_id, 'New chat inherited history');
    assert(!stats.requests[8].previous_investigation_id, 'Period change retained context');
    assert(window.__browserErrors.length===0,window.__browserErrors.join(';'));
    sessionStorage.setItem('reload-check','yes'); location.reload();
  }
} catch(error) {
  document.body.dataset.browserResult='failed'; document.body.dataset.browserError=error.message;
}
} else {

  // Node's built-in WebSocket drives the installed Edge; no automation package.
  const fs = await import('node:fs');
  const config = JSON.parse(process.env.UI_CDP_CONFIG);
  const target = await (await fetch('http://127.0.0.1:' + config.port +
    '/json/new?about:blank', {method: 'PUT'})).json();
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once: true});
    socket.addEventListener('error', reject, {once: true});
  });
  let sequence = 0;
  const pending = new Map(), errors = [], assets = [], knownNetworkErrors = [],
    browserEnvironmentErrors = [];
  socket.addEventListener('message', event => {
    const data = JSON.parse(event.data);
    if (data.id) {
      const item = pending.get(data.id); if (!item) return;
      pending.delete(data.id);
      if (data.error) item.reject(Error(data.error.message)); else item.resolve(data.result);
    }
    if (data.method === 'Runtime.exceptionThrown')
      errors.push(data.params.exceptionDetails.text + ': ' +
        (data.params.exceptionDetails.exception?.description || ''));
    if (data.method === 'Runtime.consoleAPICalled' && data.params.type === 'error')
      errors.push(data.params.args.map(x => x.value || x.description).join(' '));
    if (data.method === 'Log.entryAdded' && data.params.entry.level === 'error') {
      const entry = data.params.entry;
      // Edge can emit extension-manifest CSP errors from an isolated world.
      // That policy contains chrome-extension:// and is not the served app CSP.
      if (entry.url?.startsWith('chrome-extension://') || (!entry.url &&
          entry.text.includes('Content Security Policy') && entry.text.includes('chrome-extension://')))
        browserEnvironmentErrors.push(entry.text);
      else if (entry.url?.endsWith('/favicon.ico')) knownNetworkErrors.push(entry.text);
      else errors.push((entry.url || '(no URL)') + ': ' + entry.text);
    }
    if (data.method === 'Network.responseReceived') {
      const response = data.params.response;
      if (response.url.includes('/static/')) assets.push({
        url: response.url, status: response.status, mime: response.mimeType});
    }
    if (data.method === 'Network.loadingFailed' && !data.params.canceled)
      errors.push(data.params.errorText);
  });
  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence; pending.set(id, {resolve, reject});
      socket.send(JSON.stringify({id, method, params}));
    });
  }
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Log.enable');
  await send('Page.bringToFront');
  await send('Emulation.setFocusEmulationEnabled', {enabled: true});
  await send('Emulation.setDeviceMetricsOverride', {
    width: config.width, height: config.height, deviceScaleFactor: 1,
    mobile: config.width < 600
  });
  await send('Page.navigate', {url: config.url});
  const deadline = Date.now() + 45000;
  let status = null;
  while (Date.now() < deadline) {
    const value = await send('Runtime.evaluate', {expression:
      'document.body && (document.body.dataset.browserResult || document.body.dataset.savedResult)',
      returnByValue: true});
    status = value.result.value;
    if (status === 'passed' || status === 'failed') break;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  const metrics = await send('Runtime.evaluate', {expression:
    '({width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth > innerWidth})',
    returnByValue: true});
  const dom = await send('Runtime.evaluate', {expression: 'document.documentElement.outerHTML',
    returnByValue: true});
  // Real keyboard navigation must reach a control with a visible focus outline.
  await send('Runtime.evaluate', {expression:
    'document.activeElement?.blur(); window.scrollTo(0,0)'});
  await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Tab',
    code: 'Tab', windowsVirtualKeyCode: 9});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Tab',
    code: 'Tab', windowsVirtualKeyCode: 9});
  const focus = await send('Runtime.evaluate', {expression:
    '({tag: document.activeElement.tagName, outline: getComputedStyle(document.activeElement).outlineStyle})',
    returnByValue: true});
  const evidenceBefore = await send('Runtime.evaluate', {expression:
    '(() => {const s=document.querySelector(".evidence-toggle > summary");' +
    'if(!s)return null;s.focus();return s.parentElement.open;})()', returnByValue: true});
  await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter',
    code: 'Enter', windowsVirtualKeyCode: 13});
  await send('Input.dispatchKeyEvent', {type: 'char', key: 'Enter', text: '\r',
    unmodifiedText: '\r', code: 'Enter', windowsVirtualKeyCode: 13});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter',
    code: 'Enter', windowsVirtualKeyCode: 13});
  await new Promise(resolve => setTimeout(resolve, 50));
  const evidenceAfter = await send('Runtime.evaluate', {expression:
    'document.querySelector(".evidence-toggle")?.open', returnByValue: true});
  const keyboardEvidence = evidenceBefore.result.value !== evidenceAfter.result.value;
  await send('Runtime.evaluate', {expression:
    'document.querySelector(".evidence-toggle").open = false'});
  await send('Runtime.evaluate', {expression:
    'document.activeElement?.blur(); window.scrollTo(0,0)'});
  const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  fs.writeFileSync(config.screenshot, Buffer.from(shot.data, 'base64'));
  if (config.marker === 'saved') {
    await send('Runtime.evaluate', {expression:
      'document.querySelector(".turn-result").scrollIntoView({block:"start"})'});
    const resultsShot = await send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: false});
    fs.writeFileSync(config.screenshot.replace('.png', '-results.png'),
      Buffer.from(resultsShot.data, 'base64'));
    await send('Runtime.evaluate', {expression:
      'document.querySelector(".evidence-toggle").open=true;' +
      'document.querySelector(".evidence-toggle").scrollIntoView({block:"start"})'});
    const evidenceShot = await send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: false});
    fs.writeFileSync(config.screenshot.replace('.png', '-evidence.png'),
      Buffer.from(evidenceShot.data, 'base64'));
  }
  console.log(JSON.stringify({status, dom: dom.result.value, errors, assets,
    viewport: metrics.result.value, focus: focus.result.value, keyboardEvidence,
    knownNetworkErrors, browserEnvironmentErrors}));
  await send('Browser.close');
}

