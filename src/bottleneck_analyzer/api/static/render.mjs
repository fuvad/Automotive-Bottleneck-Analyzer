// Retrieved and model content is text only; never interpreted as HTML.
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
const words = text => String(text || 'Unavailable').replaceAll('_', ' ');
const present = value => value === null || value === undefined || value === '' ? 'Not supplied' : String(value);
export function numeric(value) {
  const node = element('span', value == null ? 'Not supplied' :
    new Intl.NumberFormat('en-US', {maximumFractionDigits: 3}).format(value));
  if (value != null) { node.dataset.value = String(value); node.title = String(value); }
  return node;
}
export function dateLabel(value) {
  if (!value) return 'Not supplied';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toISOString().replace('T', ' ').replace('.000Z', ' UTC').replace('Z', ' UTC');
}
export function statusBadge(status) {
  const labels = {completed: 'Completed', incomplete: 'Incomplete', clarification_required: 'Clarification required',
    unsupported: 'Unsupported request', failed: 'Failed', active: 'Running', accepted: 'Accepted',
    pending: 'Waiting', unconfirmed: 'Execution unconfirmed', not_started: 'Not started', finalized: 'Final audit confirmed'};
  const tone = status === 'completed' ? 'success' : ['active', 'accepted', 'pending'].includes(status) ? 'running' :
    status === 'failed' ? 'failure' : ['incomplete', 'clarification_required', 'unsupported', 'unconfirmed', 'not_started'].includes(status) ? 'warning' : '';
  const badge = element('span', labels[status] || words(status), 'badge ' + tone);
  badge.dataset.status = status;
  return badge;
}
function list(items, empty = 'None supplied.') {
  if (!items?.length) return element('p', empty, 'muted');
  const node = element('ul', null, 'readable-list');
  items.forEach(item => node.append(element('li', item)));
  return node;
}
function table(headers, rows, label) {
  const outer = element('div', null, 'scroll');
  outer.tabIndex = 0; outer.setAttribute('role', 'region'); outer.setAttribute('aria-label', label);
  const node = element('table'), head = element('thead'), headerRow = element('tr');
  headers.forEach(label => { const th = element('th', label); th.scope = 'col'; headerRow.append(th); });
  head.append(headerRow); node.append(head);
  const body = element('tbody');
  for (const row of rows) {
    const tr = element('tr');
    for (const value of row) {
      const td = element('td');
      td.append(value instanceof Node ? value : typeof value === 'number' ? numeric(value) : document.createTextNode(present(value)));
      tr.append(td);
    }
    body.append(tr);
  }
  node.append(body); outer.append(node); return outer;
}
export function renderProgress(target, progress) {
  const status = progress.final_confirmed ? progress.outcome || 'finalized' : progress.execution;
  const row = element('div', null, 'progress-status');
  row.append(statusBadge(status));
  if (progress.final_confirmed) row.append(element('span', 'Final audit confirmed', 'muted'));
  target.replaceChildren(row, element('p', 'Saved checkpoints · recorded only after each component finishes.', 'progress-note'));
  if (!progress.events?.length) target.append(element('p', 'Waiting for the first persisted workflow event.', 'muted'));
  else {
    const events = element('ol', null, 'checkpoint-list');
    for (const event of progress.events) {
      const item = element('li');
      item.append(element('span', words(event.component)), statusBadge(event.status));
      const duration = element('span', null, 'duration'); duration.append(numeric(event.duration_seconds), ' s');
      item.append(duration); events.append(item);
    }
    target.append(events);
  }
  if (!progress.final_confirmed && progress.execution !== 'active') target.append(element('p',
    progress.execution === 'not_started' ? 'Admission ended before graph execution. No final result is available.' :
      'Execution is unconfirmed. This process cannot resume an interrupted investigation. Reconnect or inspect saved history.', 'notice warning'));
}
// Ranking indicators are normalized signals, not measured percentages.
export function plainIndicators(items = []) {
  const translations = [
    ['High processing/fault occupancy', 'The station spends much of its scheduled time processing vehicles or stopped by faults.'],
    ['High relative service demand', 'This station needs relatively more processing time for the selected model.'],
    ['Input queue accumulation', 'Vehicles build up in the queue before the station.'],
    ['Upstream blocking', 'Earlier stations are held up waiting to pass vehicles onward.'],
    ['Downstream starvation', 'Later stations wait for vehicles to arrive.'],
    ['Substantial own blocking', 'This station also waits for space downstream, which may point to a restriction later in the line.'],
    ['Substantial own starvation', 'This station also waits for incoming vehicles, which may point to a restriction earlier in the line.'],
    ['Queue occupancy unavailable', 'Queue measurements were unavailable.'],
    ['Active service samples unavailable', 'Processing-time samples were unavailable.'],
    ['Shared machine states', 'Machine-state time is shared across vehicle models, which limits this comparison.'],
  ];
  return [...new Set(items.map(item => translations.find(([key]) => item.startsWith(key))?.[1]).filter(Boolean))].slice(0, 3);
}

export function selectSourceRecords(bundle) {
  const assessments = [...(bundle?.assessments || []), ...(bundle?.interpretations || [])];
  const support = new Set(assessments.flatMap(a => a.evidence_ids || []));
  const conflict = new Set(assessments.flatMap(a => a.conflicting_evidence_ids || []));
  const seen = new Set();
  const records = [...(bundle?.records || [])].sort((a,b) =>
    Number(conflict.has(b.evidence_id)) - Number(conflict.has(a.evidence_id))).filter(record => {
    const key = [record.source_system, record.text, record.document_version].join('|');
    if (seen.has(key)) return false;
    seen.add(key); return true;
  }).map(record => ({...record, role: conflict.has(record.evidence_id) ? 'limiting' :
    support.has(record.evidence_id) ? 'supporting' : 'related'}));
  const limiting = records.find(r => r.role === 'limiting');
  const useful = records.filter(r => r.role !== 'limiting')
    .sort((a,b) => Number(b.role === 'supporting') - Number(a.role === 'supporting'));
  // Prefer different source systems over repeated excerpts from the same system.
  const diverse = rows => {
    const first = [], systems = new Set();
    for (const record of rows) if (!systems.has(record.source_system)) {
      first.push(record); systems.add(record.source_system);
    }
    return [...first, ...rows.filter(r => !first.includes(r))];
  };
  const ordered = [...diverse(useful.filter(r => r.role === 'supporting')),
    ...diverse(useful.filter(r => r.role === 'related'))];
  return [...ordered.slice(0, limiting ? 2 : 3), ...(limiting ? [limiting] : [])];
}

function evidenceSection(title) {
  const node = element('section', null, 'evidence-section');
  node.append(element('h3', title)); return node;
}
function sentence(...parts) {
  const node = element('p');
  for (const part of parts) node.append(typeof part === 'number' ? numeric(part) : part);
  return node;
}
function historicalEvidence(result) {
  const h = result.historical;
  if (!h) return null;
  const node = evidenceSection(h.leading_candidate ? 'Why ' + h.leading_candidate + ' stands out' : 'What the production records show');
  const indicators = plainIndicators(h.supporting_indicators);
  if (indicators.length) node.append(list(indicators));
  else node.append(element('p', 'The saved result does not include a clear set of supporting station indicators.'));
  if (['weak','insufficient_evidence'].includes(h.evidence_strength))
    node.append(element('p', 'Support for this conclusion is limited; the records do not establish a clear bottleneck.', 'notice warning'));
  node.append(element('h4', 'How the output was measured'));
  if (h.scheduled_hours > 0 && h.historical_jph != null) {
    node.append(sentence(h.completed, ' completed bodies ÷ ', h.scheduled_hours,
      ' scheduled hours = ', h.historical_jph, ' bodies per hour.'));
  } else node.append(element('p', 'There is no usable scheduled-hours denominator for an hourly output rate.'));
  const design = result.historical_provenance?.line?.design_rate_jph;
  if (h.design_gap_jph != null) {
    node.append(design != null ? sentence('Design reference: ', design, ' bodies per hour. Gap: ',
      h.design_gap_jph, ' bodies per hour.') :
      sentence('The recorded gap to the design reference is ', h.design_gap_jph, ' bodies per hour.'));
  }
  if (result.scope?.model) node.append(element('p', 'This model rate is its share of mixed-line output, not the capacity of a line making only that model.', 'notice'));
  const limits = plainIndicators(h.conflicting_indicators);
  if (h.conflicting_indicators?.length) {
    node.append(element('h4', 'What makes this less certain'), list(limits.length ? limits :
      ['Some indicators disagree with the candidate or could not be checked.']));
  }
  node.append(element('p', 'These historical signals identify a candidate, not a proven cause. The design gap is not the gain a single fix would necessarily recover.', 'notice'));
  return node;
}
function comparisonEvidence(result) {
  const segments = result.historical?.segments || [];
  const node = evidenceSection('Comparisons behind the answer');
  if (!segments.length) {
    node.append(element('p', 'No comparison groups were supplied for this result.')); return node;
  }
  // Start with a few representative examples, including unresolved or differing candidates.
  const examples = [], groups = new Set();
  for (const segment of segments) {
    const key = [segment.kind, segment.leading_candidate].join('|');
    if (!groups.has(key)) { examples.push(segment); groups.add(key); }
  }
  for (const segment of segments) if (examples.length < 6 && !examples.includes(segment)) examples.push(segment);
  const shown = examples.slice(0, 6);
  const container = element('div');
  const show = rows => container.replaceChildren(table(
    ['Group', 'Candidate', 'Bodies/hour'], rows.map(s => [
      s.label, s.leading_candidate || 'Not established', s.jph
    ]), 'Compared production groups'));
  show(shown); node.append(element('p', 'The answer uses the available shift, model and time-of-day groups. A few examples are shown below.'), container);
  if (segments.length > shown.length) {
    const button = element('button', 'Show all comparison groups', 'text-button'); button.type = 'button';
    let expanded = false;
    button.onclick = () => { expanded = !expanded; show(expanded ? segments : shown);
      button.textContent = expanded ? 'Show fewer examples' : 'Show all comparison groups'; };
    node.append(button);
  }
  node.append(element('p', 'Model rates are shares of mixed-line output. Groups without a clear candidate remain inconclusive.', 'notice'));
  return node;
}
function sourceEvidence(result) {
  const bundle = result.evidence, node = evidenceSection('Records behind the explanation');
  const chosen = selectSourceRecords(bundle);
  if (!chosen.length) node.append(element('p', 'No usable source passages were returned for this question.'));
  const names = {CMMS: 'Maintenance work order', SCADA: 'Equipment fault record', Andon: 'Operator call',
    shift_notes: 'Shift note', historian: 'Sensor record', SOP: 'Procedure'};
  for (const record of chosen) {
    const item = element('article', null, 'evidence-item');
    item.dataset.sourceId = record.source_id || record.source_record_id || '';
    item.append(element('h4', (names[record.source_system] || 'Source record') +
      (record.station ? ' · ' + record.station : '')));
    const meta = [];
    if (record.recorded_at) meta.push(dateLabel(record.recorded_at));
    if (record.document_version) meta.push('Version ' + record.document_version);
    item.append(element('p', meta.join(' · '), 'evidence-subtitle'));
    const full = record.text || '', short = full.length > 400 ? full.slice(0,400) + '…' : full;
    const quote = element('blockquote', short, 'passage'); item.append(quote);
    if (short !== full) {
      const more = element('button', 'Read full passage', 'text-button'); more.type = 'button';
      let expanded = false;
      more.onclick = () => { expanded = !expanded; quote.textContent = expanded ? full : short;
        more.textContent = expanded ? 'Show shorter excerpt' : 'Read full passage'; };
      item.append(more);
    }
    const relationship = record.relationship === 'direct' ? 'Linked directly to the incident or record.' :
      record.relationship === 'inferred' ? 'The link is inferred; it is not a confirmed incident match.' :
      'Related search result; an incident link is not confirmed.';
    item.append(element('p', relationship, 'notice'));
    if (record.role === 'limiting') item.append(element('p', 'This record conflicts with the explanation or was excluded from supporting it.', 'notice warning'));
    else if (record.role === 'related') item.append(element('p', 'Related context; it was not cited as support for the explanation.', 'notice'));
    node.append(item);
  }
  if ((bundle?.records?.length || 0) > chosen.length)
    node.append(element('p', 'Showing a few representative passages. Additional records remain in the saved investigation.', 'notice'));
  if (bundle?.unavailable_methods?.length)
    node.append(element('p', 'Some evidence searches were unavailable, so this is a partial check.', 'notice warning'));
  node.append(element('p', 'A maintenance note or matching record can support an explanation without proving the cause of every stop.', 'notice'));
  return node;
}
function simulationEvidence(result) {
  const s = result.simulation, node = evidenceSection('What the simulation tested');
  if (!s) { node.append(element('p', 'No completed simulation result was supplied.')); return node; }
  const request = s.scenario_request?.request;
  if (['repair_duration','failure_rate'].includes(request?.method)) {
    const method = request.method === 'repair_duration' ? 'shorter repair times' : 'a lower failure rate';
    node.append(sentence('Tested change: ', request.reduction_percentage, '% ', method,
      request.target_station && request.target_station !== 'candidate' ? ' at ' + request.target_station + '.' : ' at the selected station.'));
  }
  node.append(table(['Modelled output', 'Bodies/hour'], [
    ['Without the change', s.baseline.mean], ['With the change', s.scenario.mean],
    ['Estimated change', s.paired_gain.mean]
  ], 'Simulation evidence'));
  node.append(sentence('Compared ', s.paired_gain.n, ' baseline-and-change runs, each covering ',
    s.days, ' simulated days.'));
  if (s.paired_gain.ci95) node.append(sentence('95% confidence interval for the change: ',
    s.paired_gain.ci95[0], ' to ', s.paired_gain.ci95[1], ' bodies per hour.'));
  node.append(element('p', 'This interval describes variation between simulation runs. It does not guarantee the same gain in a real plant.', 'notice'));
  return node;
}
export function renderEvidence(target, result) {
  const intent = result.intent || 'constraint_output_loss';
  const sections = [];
  if (['constraint_output_loss','combined'].includes(intent) && result.historical)
    sections.push(historicalEvidence(result));
  if (intent === 'segmentation') sections.push(comparisonEvidence(result));
  if (['causes','combined'].includes(intent)) sections.push(sourceEvidence(result));
  if (['what_if','combined'].includes(intent)) sections.push(simulationEvidence(result));
  target.replaceChildren(...sections.filter(Boolean));
  if (!sections.length) target.append(element('p', result.outcome === 'clarification_required' ?
    'This question needs clarification before evidence can be gathered.' :
    'This investigation did not return evidence for a reliable answer.'));
  if (result.outcome === 'incomplete' || result.errors?.length)
    target.append(element('p', 'This result is partial or failed. Check the outcome before relying on the available findings.', 'notice warning'));
  if (result.errors?.length) target.append(element('p',
    'What stopped the investigation: ' + result.errors[0].message.slice(0,300), 'notice warning'));
  target.append(element('p', 'Based on synthetic records for the selected dataset and period.', 'notice'));
}

export function renderResult(target, result) {
  const answer = element('div', null, 'answer');
  for (const paragraph of (result.answer || 'No answer was returned.').split(/\n\s*\n/)) {
    // Source-ID excerpts remain verbatim inside View evidence and the full answer.
    if (/^\[[\da-f-]{36}\]/i.test(paragraph) || paragraph === result.human_review) continue;
    answer.append(element('p', paragraph));
  }
  if (result.intent === 'segmentation' && result.historical &&
      ['completed', 'incomplete'].includes(result.outcome)) {
    const models = (result.historical.segments || []).filter(s => s.kind === 'model');
    if (models.length) {
      const comparison = table(['Vehicle model', 'Historical candidate', 'JPH contribution', 'Completions'],
        models.map(s => [s.label, s.leading_candidate || 'Not established', s.jph, s.completed]),
        'Vehicle model comparison');
      comparison.classList.add('answer-comparison');
      answer.append(comparison);
    }
    answer.append(element('p', 'The main comparison evidence is under View evidence.', 'notice'));
  }
  const status = element('div', null, 'answer-status');
  status.append(statusBadge(result.outcome));
  const copy = element('button', 'Copy investigation ID', 'text-button copy-id');
  copy.type = 'button'; copy.title = result.investigation_id || result.audit_id || 'ID not supplied';
  copy.disabled = !result.investigation_id && !result.audit_id;
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(result.investigation_id || result.audit_id); copy.textContent = 'ID copied'; }
    catch { copy.textContent = copy.title; }
  };
  const details = element('details', null, 'evidence-toggle');
  const body = element('div', null, 'evidence-body');
  renderEvidence(body, result);
  if (result.outcome === 'completed') body.append(status);
  body.append(copy);
  details.append(element('summary', 'View evidence'), body);
  target.replaceChildren(...(result.outcome === 'completed' ? [] : [status]), answer);
  if (result.clarification && !result.answer?.includes(result.clarification))
    target.append(element('p', result.clarification));
  target.append(details);
}

