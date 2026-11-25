import assert from 'node:assert/strict';
import { deriveEtaTelemetry, resolveCompletedQaState } from '../src/lib/telemetry.ts';

const at = 1_700_000_000_000;

const missing = deriveEtaTelemetry({
  status: 'running',
  progress: 0.25,
  durationSeconds: 100,
  realTimeFactor: 0.8,
  nowMs: at,
});
assert.equal(missing.remainingSeconds, null, 'missing persisted elapsed must stay unavailable');
assert.equal(missing.completionAtMs, null, 'missing persisted elapsed must not produce a clock');

const nonFinite = deriveEtaTelemetry({
  status: 'running',
  progress: 0.25,
  elapsedSeconds: 10,
  durationSeconds: Number.NaN,
  realTimeFactor: 0.8,
  nowMs: at,
});
assert.equal(nonFinite.remainingSeconds, null, 'non-finite duration must stay unavailable');

const zeroTotal = deriveEtaTelemetry({
  status: 'running',
  progress: 0,
  elapsedSeconds: 0,
  durationSeconds: 0,
  realTimeFactor: 0.8,
  nowMs: at,
});
assert.equal(zeroTotal.remainingSeconds, null, 'zero duration must stay unavailable');

const partial = deriveEtaTelemetry({
  status: 'running',
  progress: 0.5,
  elapsedSeconds: 10,
  durationSeconds: 100,
  realTimeFactor: 0.8,
  nowMs: at,
});
assert.equal(partial.remainingSeconds, 10, 'partial progress uses persisted elapsed time');
assert.equal(partial.completionAtMs, at + 10_000, 'completion clock follows finite ETA');

const initial = deriveEtaTelemetry({
  status: 'running',
  progress: 0,
  elapsedSeconds: 0,
  durationSeconds: 100,
  realTimeFactor: 0.8,
  nowMs: at,
});
assert.equal(initial.remainingSeconds, 80, 'zero progress may estimate from persisted duration and RTF');

assert.equal(resolveCompletedQaState(null), null, 'missing job has no completed QA state');
assert.equal(
  resolveCompletedQaState({ status: 'running', result: { qa: { passed: true } } }),
  null,
  'non-completed job must not claim a final QA state',
);
assert.equal(
  resolveCompletedQaState({ status: 'completed', result: { qa: { passed: false } } }),
  'failed',
  'completed job with qa.passed=false (Job12) must resolve to failed',
);
assert.equal(
  resolveCompletedQaState({ status: 'completed', result: { qa: { passed: true } } }),
  'passed',
  'completed job with qa.passed=true must resolve to passed',
);
assert.equal(
  resolveCompletedQaState({ status: 'completed', result: { qa: { passed: null } } }),
  'unverified',
  'completed job with qa.passed=null must resolve to unverified',
);
assert.equal(
  resolveCompletedQaState({ status: 'completed', result: null }),
  'unverified',
  'completed job without QA metadata must resolve to unverified',
);
assert.equal(
  resolveCompletedQaState({ status: 'completed', result: { qa: { passed: 'true' } } }),
  'unverified',
  'non-boolean QA passed value must not pass',
);

console.log(JSON.stringify({ status: 'PASS', cases: 12 }));
