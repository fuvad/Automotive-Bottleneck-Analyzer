import {api, makeRequest, pollOnce, retryDelay, contextParent, utcInput} from './client.mjs';
import {element, renderProgress, renderResult} from './render.mjs';

const $ = id => document.getElementById(id);
const storageKey = 'bottleneck-current-chat-v1';
let chat = {version: 1, turns: []}, datasets = [], generation = 0, busy = false;
function message(value, error = false) { $('message').textContent = value; $('message').className = error ? 'error' : ''; }
function lock(value) {
  busy = value;
  for (const id of ['submit', 'new-chat', 'dataset', 'start', 'end']) $(id).disabled = value;
}
function selection() {
  return {dataset: $('dataset').value, start_time: $('start').value ? $('start').value + 'Z' : undefined,
    end_time: $('end').value ? $('end').value + 'Z' : undefined};
}
function scroll() { $('conversation').scrollTop = $('conversation').scrollHeight; }
function display(turn) {
  $('welcome').hidden = true;
  const article = element('article', null, 'turn'), question = element('div', turn.question || 'Saved question', 'user-message');
  const scope = turn.scope || {};
  const scopeLine = element('div', [scope.dataset, scope.start_time, scope.end_time].filter(Boolean).join(' · '), 'turn-scope');
  const assistant = element('div', null, 'assistant'), progress = element('div', null, 'turn-progress'), result = element('div', null, 'turn-result');
  assistant.append(element('div', 'Analyzer', 'assistant-label'), progress, result);
  article.append(question, scopeLine, assistant); $('thread').append(article);
  turn.view = {article, question, scopeLine, progress, result};
  return turn.view;
}
// Persist request identifiers and scope only; large answers and evidence stay in their audits.
function persist() {
  const stored = {version: 1, selection: selection(), turns: chat.turns.map(({view, ...turn}) => turn)};
  localStorage.setItem(storageKey, JSON.stringify(stored));
}
async function monitor(turn, version = generation) {
  const view = turn.view || display(turn);
  let failures = 0;
  while (version === generation) {
    try {
      const status = await pollOnce(turn.id);
      if (version !== generation) return;
      failures = 0; renderProgress(view.progress, status.progress);
      if (status.result) {
        const result = status.result;
        view.progress.hidden = true;
        turn.final = true; turn.scope = result.scope; turn.question = result.question;
        view.question.textContent = turn.question;
        view.scopeLine.textContent = [result.scope.dataset, result.scope.start_time, result.scope.end_time].filter(Boolean).join(' · ');
        renderResult(view.result, result);
        persist(); lock(false); $('refresh').hidden = true;
        message(''); scroll(); return;
      }
      if (!status.keepPolling) {
        lock(false); $('submit').disabled = true; $('refresh').hidden = false;
        message('No final audit is confirmed. Reconnect to check; this is not a cancellation.', true); return;
      }
      await new Promise(resolve => setTimeout(resolve, 2000));
    } catch (error) {
      if (version !== generation) return;
      $('refresh').hidden = false;
      if ([404, 409, 422].includes(error.status)) {
        lock(false); $('submit').disabled = true;
        message(error.message + ' Reconnect to check the saved investigation.', true); return;
      }
      message('Connection interrupted. Retrying saved progress by GET; no question is resubmitted.', true);
      await new Promise(resolve => setTimeout(resolve, retryDelay(failures++)));
    }
  }
}
async function reconcile(turn) {
  lock(true); message('Checking whether the initial audit was committed…');
  try {
    const {payload} = await api('/api/submissions/' + encodeURIComponent(turn.key));
    if (payload.admission === 'accepted' && payload.investigation_id) {
      turn.id = payload.investigation_id; persist(); await monitor(turn); return;
    }
    lock(payload.worker_active);
    $('submit').disabled = true; $('refresh').hidden = false;
    message('Submission ' + payload.admission + '. ' + (payload.worker_active ?
      'A worker is still active. Reconnect to check again.' :
      'No accepted execution is confirmed. Start a new chat only after reviewing this uncertainty; no cancellation is implied.'), true);
  } catch {
    lock(false); $('submit').disabled = true; $('refresh').hidden = false;
    message('Admission cannot be reconciled in this process. The previous request may still have an audit. No automatic resubmission will occur.', true);
  }
}
$('question-form').onsubmit = async event => {
  event.preventDefault(); if (busy) return;
  const question = $('question').value.trim(); if (question.length < 3) return;
  const scope = selection();
  if (!scope.dataset) { message('Select an available dataset.', true); return; }
  if (scope.start_time && scope.end_time && scope.start_time >= scope.end_time) {
    message('The end must be later than the start.', true); return;
  }
  const request = makeRequest({...scope, question, previous_investigation_id: contextParent(chat.turns, scope)});
  const turn = {question, scope, key: crypto.randomUUID(), final: false};
  chat.turns.push(turn);
  try { persist(); } catch {
    chat.turns.pop(); message('Browser storage is unavailable. Enable local storage before sending so a refresh cannot lose the submission key.', true); return;
  }
  display(turn); lock(true); $('question').value = ''; scroll();
  message('Waiting for the initial audit to commit…');
  try {
    const {payload} = await api('/api/investigations', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Submission-Key': turn.key}, body: JSON.stringify(request)});
    turn.id = payload.investigation_id; persist(); message('Accepted. Showing saved checkpoints.');
    await monitor(turn);
  } catch {
    $('refresh').hidden = false;
    // The server may have committed after a lost response. Resolve the key by GET.
    await reconcile(turn);
  }
};
$('question').onkeydown = event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault(); if (!busy && !$('submit').disabled) $('question-form').requestSubmit();
  }
};
$('refresh').onclick = async () => {
  const turn = chat.turns.at(-1); if (!turn) return;
  ++generation; lock(true);
  if (turn.id) await monitor(turn); else await reconcile(turn);
};
$('new-chat').onclick = () => {
  if (busy) return;
  ++generation; chat = {version: 1, turns: []}; persist();
  localStorage.removeItem('investigation'); localStorage.removeItem('submission');
  const url = new URL(location.href); url.searchParams.delete('investigation'); history.replaceState(null, '', url);
  $('thread').replaceChildren(); $('welcome').hidden = false; $('question').value = '';
  $('refresh').hidden = true; lock(false); message('New chat. Saved audit records are retained.'); $('question').focus();
};
function changed() {
  try { persist(); message('This scope applies to your next question. Context is reused only for the same dataset and period.'); }
  catch { message('Browser storage unavailable.', true); }
}
function datasetDates() {
  const dataset = datasets.find(d => d.name === $('dataset').value);
  if (!dataset) return;
  $('start').value = utcInput(dataset.start_time); $('end').value = utcInput(dataset.end_time);
}
$('dataset').onchange = () => { datasetDates(); changed(); };
$('start').onchange = changed; $('end').onchange = changed;
for (const [label, question] of [
  ['Find the constraint', 'Which station is the strongest historical bottleneck candidate and what is the output gap?'],
  ['Compare shifts & models', 'Does the historical candidate differ by shift or SUV versus Sedan?'],
  ['Explain interruptions', 'What maintenance evidence may explain interruptions at Hemming?'],
  ['Explore a what-if', 'What would a 30% reduction in robot repair duration at Hemming change?'],
]) {
  const button = element('button', label); button.type = 'button';
  button.onclick = () => { $('question').value = question; $('question').focus(); };
  $('examples').append(button);
}
async function initialize() {
  lock(true);
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (stored?.version === 1 && Array.isArray(stored.turns)) chat = stored;
    const {payload} = await api('/api/datasets?limit=50'); datasets = payload;
    $('dataset').replaceChildren(element('option', 'Select a dataset'));
    $('dataset').options[0].value = '';
    for (const dataset of datasets) {
      const option = element('option', dataset.name); option.value = dataset.name; $('dataset').append(option);
    }
    $('dataset').value = datasets.some(d => d.name === chat.selection?.dataset) ? chat.selection.dataset :
      datasets.find(d => d.name === 'sim-30day-baseline-v1')?.name || datasets[0]?.name || '';
    datasetDates();
    if (chat.selection?.dataset === $('dataset').value) {
      $('start').value = (chat.selection.start_time || '').replace(/Z$/, '');
      $('end').value = (chat.selection.end_time || '').replace(/Z$/, '');
    }
    if (!chat.turns.length) {
      const id = new URL(location.href).searchParams.get('investigation') || localStorage.getItem('investigation');
      const key = localStorage.getItem('submission');
      if (key) chat.turns.push({key, question: 'Restoring previous submission', scope: selection()});
      else if (id) chat.turns.push({id, question: 'Saved investigation', scope: selection()});
    }
    for (const turn of chat.turns) display(turn);
    // Restore finalized exchanges with GET only, then reconcile the sole pending exchange.
    for (const turn of chat.turns) {
      if (turn.final && turn.id) {
        try {
          const {payload} = await api('/api/investigations/' + encodeURIComponent(turn.id) + '/result');
          renderResult(turn.view.result, payload); turn.view.question.textContent = payload.question;
        } catch { turn.view.result.textContent = 'Saved answer unavailable. Its audit has not been deleted.'; }
      }
    }
    const last = chat.turns.at(-1);
    if (last && !last.final) {
      if (last.id) await monitor(last); else await reconcile(last);
    } else lock(false);
    $('welcome').hidden = chat.turns.length > 0;
    document.body.dataset.chatReady = 'true'; scroll();
  } catch {
    lock(false); $('submit').disabled = true;
    message('Datasets or browser storage unavailable. Check PostgreSQL and local storage, then reload.', true);
    document.body.dataset.chatReady = 'error';
  }
}
initialize();
