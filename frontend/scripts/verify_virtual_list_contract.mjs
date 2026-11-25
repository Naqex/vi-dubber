import assert from 'node:assert/strict';
import {
  buildTimelineBuckets,
  buildVirtualLayout,
  computeVirtualWindow,
  DEFAULT_MAX_TIMELINE_BUCKETS,
  DEFAULT_VIRTUAL_ROW_HEIGHT,
} from '../src/lib/virtualList.ts';

// 1. 10,000-segment 12-hour synthetic fixture
const COUNT = 10_000;
const DURATION_SECONDS = 43_200; // 12 hours
const step = DURATION_SECONDS / COUNT;
const segments = Array.from({ length: COUNT }, (_, idx) => ({
  id: idx,
  start: idx * step,
  end: (idx + 1) * step - 0.1,
  speaker: idx % 2 === 0 ? 'SPEAKER_00' : 'SPEAKER_01',
  flagged: idx % 250 === 0,
  review_status: idx % 500 === 0 ? 'needs_review' : 'unreviewed',
}));

const layout = buildVirtualLayout(segments);
assert.equal(layout.totalHeight, COUNT * DEFAULT_VIRTUAL_ROW_HEIGHT, 'uniform initial total height must be exact');

const topWindow = computeVirtualWindow(layout, 0, 720, 6);
assert.equal(topWindow.startIndex, 0);
assert.ok(topWindow.endIndex - topWindow.startIndex < 30, 'top window must mount < 30 rows for 10k segments');
assert.equal(topWindow.topSpacerHeight, 0);
assert.equal(
  topWindow.topSpacerHeight +
    (layout.offsets[topWindow.endIndex] - layout.offsets[topWindow.startIndex]) +
    topWindow.bottomSpacerHeight,
  layout.totalHeight,
  'spacers + mounted window height must preserve exact total scroll height',
);

const midScroll = 5_000 * DEFAULT_VIRTUAL_ROW_HEIGHT;
const midWindow = computeVirtualWindow(layout, midScroll, 720, 6);
assert.ok(midWindow.startIndex <= 5_000 && midWindow.endIndex > 5_000, 'mid window must include scrolled row');
assert.ok(midWindow.endIndex - midWindow.startIndex < 30, 'mid window must stay bounded < 30 rows');

const endWindow = computeVirtualWindow(layout, layout.totalHeight, 720, 6);
assert.equal(endWindow.endIndex, COUNT, 'bottom window must reach final segment');
assert.equal(endWindow.bottomSpacerHeight, 0, 'bottom spacer must be zero at list end');
assert.ok(endWindow.endIndex - endWindow.startIndex < 30, 'bottom window must stay bounded < 30 rows');

// Variable measured row heights
const measured = new Map([[0, 240], [1, 310], [5_000, 260]]);
const measuredLayout = buildVirtualLayout(segments, measured);
assert.equal(
  measuredLayout.totalHeight,
  layout.totalHeight + (240 - DEFAULT_VIRTUAL_ROW_HEIGHT) + (310 - DEFAULT_VIRTUAL_ROW_HEIGHT) + (260 - DEFAULT_VIRTUAL_ROW_HEIGHT),
  'measured row heights must update cumulative total height accurately',
);

// Empty list edge case
const emptyWindow = computeVirtualWindow(buildVirtualLayout([]), 100, 720);
assert.deepEqual(emptyWindow, {
  startIndex: 0,
  endIndex: 0,
  topSpacerHeight: 0,
  bottomSpacerHeight: 0,
  totalHeight: 0,
});

// 2. Timeline marker bucketing for 10,000 segments over 12h
const buckets = buildTimelineBuckets(segments, 0, DURATION_SECONDS, 7_500);
assert.ok(buckets.length > 0 && buckets.length <= DEFAULT_MAX_TIMELINE_BUCKETS, '10k timeline markers must cap at maxBuckets (120)');
assert.ok(buckets.every(b => b.bucketed), '10k markers must use bucketed mode');
const activeBucket = buckets.find(b => b.hasActive);
assert.ok(activeBucket, 'active segment must be highlighted in its bucket');
assert.equal(activeBucket.representativeSegmentId, 7_500, 'active segment takes click-seek priority in its bucket');
const flaggedBuckets = buckets.filter(b => b.hasFlagged);
assert.ok(flaggedBuckets.length > 0, 'flagged segments must surface on the bucketed timeline');
const flaggedNonActive = flaggedBuckets.find(b => !b.hasActive);
assert.ok(flaggedNonActive && flaggedNonActive.representativeSegmentId % 250 === 0, 'flagged bucket must target a flagged segment');

// Small jobs (<= 240) stay 1-to-1 per segment
const small = segments.slice(0, 12);
const smallMarkers = buildTimelineBuckets(small, 0, 100, 3);
assert.equal(smallMarkers.length, 12, 'small job preserves exact 1-to-1 segment markers');
assert.ok(smallMarkers.every(m => !m.bucketed), 'small job must not bucket markers');

console.log(JSON.stringify({ status: 'PASS', checks: 14, buckets10k: buckets.length, mountedWindow10k: midWindow.endIndex - midWindow.startIndex }));
