import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const sourcePath = fileURLToPath(new URL('../src/index.css', import.meta.url));
const sharedSnapshotPath = fileURLToPath(new URL('../src/ui-system.snapshot.css', import.meta.url));
const systemBarPath = fileURLToPath(new URL('../src/components/header/SystemBar.tsx', import.meta.url));
const stepperPath = fileURLToPath(new URL('../src/components/pipeline/PipelineStepper.tsx', import.meta.url));
const etaCardPath = fileURLToPath(new URL('../src/components/monitor/DynamicEtaCard.tsx', import.meta.url));
const jobContextPath = fileURLToPath(new URL('../src/context/JobContext.tsx', import.meta.url));
const reviewerPath = fileURLToPath(new URL('../src/components/review/SegmentReviewer.tsx', import.meta.url));
const videoPlayerPath = fileURLToPath(new URL('../src/components/monitor/VideoPlayer.tsx', import.meta.url));
const [
  sourceCss,
  sharedSnapshotCss,
  systemBarTsx,
  stepperTsx,
  etaCardTsx,
  jobContextTsx,
  reviewerTsx,
  videoPlayerTsx,
] = await Promise.all([
  readFile(sourcePath, 'utf8'),
  readFile(sharedSnapshotPath, 'utf8'),
  readFile(systemBarPath, 'utf8'),
  readFile(stepperPath, 'utf8'),
  readFile(etaCardPath, 'utf8'),
  readFile(jobContextPath, 'utf8'),
  readFile(reviewerPath, 'utf8'),
  readFile(videoPlayerPath, 'utf8'),
]);

assert.match(sourceCss, /@media\s*\(prefers-reduced-motion:\s*reduce\)/, 'VI CSS must honor reduced-motion preferences');
assert.match(sourceCss, /animation-duration:\s*0\.001ms\s*!important/, 'reduced motion must stop long-running animations');
assert.match(sourceCss, /transition-duration:\s*0\.001ms\s*!important/, 'reduced motion must shorten transitions');
assert.match(sharedSnapshotCss, /\.ui-button:focus-visible\s*\{[^}]*outline:/s, 'shared button contract must retain visible focus');
assert.match(systemBarTsx, /resolveCompletedQaState/, 'SystemBar must distinguish completed QA states');
assert.match(systemBarTsx, /transport_mode === 'websocket'/, 'SystemBar must not display WS LIVE over HTTP polling');
assert.match(stepperTsx, /resolveCompletedQaState/, 'PipelineStepper must not render green DONE on QA failure');
assert.match(etaCardTsx, /PIPELINE_COMPLETE · QA_FAILED/, 'DynamicEtaCard must distinguish completed QA failures');
assert.match(jobContextTsx, /acceptAllJobSegments\(/, 'JobContext acceptAllSegments must use single batch endpoint');
assert.doesNotMatch(jobContextTsx, /Promise\.all\(\s*pendingSegments\.map/s, 'JobContext must not fan out per-segment PATCH storm');
assert.match(reviewerTsx, /computeVirtualWindow\(/, 'SegmentReviewer must virtualize segment cards for 12h jobs');
assert.match(videoPlayerTsx, /buildTimelineBuckets\(/, 'VideoPlayer must bound timeline markers for 12h jobs');

console.log(JSON.stringify({ status: 'PASS', checks: 12 }));
