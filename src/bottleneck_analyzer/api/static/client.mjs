export class APIError extends Error {
  constructor(status, payload) {
    super(payload?.error?.message || 'The local service could not complete this request.');
    this.status = status; this.code = payload?.error?.code; this.payload = payload;
  }
}

export async function api(path, options = {}, fetcher = fetch) {
  const response = await fetcher(path, {credentials: 'same-origin', ...options});
  const payload = await response.json();
  if (!response.ok) throw new APIError(response.status, payload);
  return {status: response.status, payload};
}

export function makeRequest(fields) {
  const scope = {dataset: fields.dataset};
  for (const key of ['station', 'model', 'shift', 'shift_id', 'start_time', 'end_time']) {
    if (fields[key]) scope[key] = fields[key];
  }
  if (fields.hours?.trim()) {
    const values = fields.hours.split(',').map(x => Number(x.trim()));
    if (values.some(x => !Number.isInteger(x) || x < 0 || x > 23)) throw new Error('UTC hours must be integers from 0 to 23.');
    scope.utc_hours = [...new Set(values)];
  }
  const request = {question: fields.question, scope};
  if (fields.previous_investigation_id) request.previous_investigation_id = fields.previous_investigation_id;
  if (fields.scenario) {
    if (!fields.target) throw new Error('Select a scenario target station.');
    request.scenario = {request: {target_station: fields.target, method: fields.method,
      reduction_percentage: Number(fields.percentage)}};
  }
  return request;
}

// Reconnect/poll is GET-only. Submissions happen only in the explicit form handler.
export async function pollOnce(id, transport = api) {
  const progress = (await transport(`/api/investigations/${encodeURIComponent(id)}`)).payload;
  if (progress.final_confirmed) {
    const result = await transport(`/api/investigations/${encodeURIComponent(id)}/result`);
    if (result.status !== 200) return {progress, result: null, keepPolling: true};
    return {progress, result: result.payload, keepPolling: false};
  }
  return {progress, result: null, keepPolling: progress.execution === 'active'};
}

export const retryDelay = attempt => Math.min(10000, 2000 * (2 ** Math.min(attempt, 3)));

export const utcInput = value => new Date(value).toISOString().slice(0, 19);

export function contextParent(turns, scope) {
  const last = turns.at(-1);
  const instant = value => value ? new Date(value).getTime() : null;
  return last?.final && last.id && last.scope?.dataset === scope.dataset &&
    instant(last.scope.start_time) === instant(scope.start_time) &&
    instant(last.scope.end_time) === instant(scope.end_time) ? last.id : undefined;
}
