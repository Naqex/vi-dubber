export const DEFAULT_VIRTUAL_ROW_HEIGHT = 168;
export const DEFAULT_VIRTUAL_OVERSCAN = 6;
export const DEFAULT_VIRTUAL_VIEWPORT_HEIGHT = 640;
export const DEFAULT_MAX_TIMELINE_BUCKETS = 120;

export interface VirtualRowIdentity {
  id: number;
}

export interface VirtualLayout {
  offsets: Float64Array;
  totalHeight: number;
}

export interface VirtualWindow {
  startIndex: number;
  endIndex: number;
  topSpacerHeight: number;
  bottomSpacerHeight: number;
  totalHeight: number;
}

/**
 * Build cumulative vertical offsets for a list of rows with optional per-id
 * measured heights. Runs in O(N) over a single Float64Array (< 0.1 ms for 10k rows).
 */
export function buildVirtualLayout(
  items: readonly VirtualRowIdentity[],
  measuredHeights?: ReadonlyMap<number, number>,
  estimatedRowHeight = DEFAULT_VIRTUAL_ROW_HEIGHT,
): VirtualLayout {
  const count = items.length;
  const fallback = Number.isFinite(estimatedRowHeight) && estimatedRowHeight > 0
    ? estimatedRowHeight
    : DEFAULT_VIRTUAL_ROW_HEIGHT;
  const offsets = new Float64Array(count + 1);
  let cursor = 0;
  for (let i = 0; i < count; i++) {
    offsets[i] = cursor;
    const measured = measuredHeights?.get(items[i].id);
    const height = typeof measured === 'number' && Number.isFinite(measured) && measured > 0
      ? measured
      : fallback;
    cursor += height;
  }
  offsets[count] = cursor;
  return { offsets, totalHeight: cursor };
}

/**
 * Binary-search the first row whose bottom edge exceeds `offsetPx`.
 */
export function findIndexAtOffset(offsets: Float64Array, offsetPx: number): number {
  const count = offsets.length - 1;
  if (count <= 0) return 0;
  if (offsetPx <= 0) return 0;
  if (offsetPx >= offsets[count]) return count - 1;

  let low = 0;
  let high = count - 1;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (offsets[mid + 1] <= offsetPx) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  return low;
}

/**
 * Compute the bounded visible slice `[startIndex, endIndex)` plus top/bottom
 * spacer heights so only visible rows + overscan are mounted in the DOM.
 */
export function computeVirtualWindow(
  layout: VirtualLayout,
  scrollTop: number,
  viewportHeight: number,
  overscan = DEFAULT_VIRTUAL_OVERSCAN,
): VirtualWindow {
  const count = layout.offsets.length - 1;
  const totalHeight = layout.totalHeight;
  if (count <= 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      topSpacerHeight: 0,
      bottomSpacerHeight: 0,
      totalHeight: 0,
    };
  }

  const safeScrollTop = Math.max(0, Number.isFinite(scrollTop) ? scrollTop : 0);
  const safeViewport = Math.max(
    1,
    Number.isFinite(viewportHeight) && viewportHeight > 0
      ? viewportHeight
      : DEFAULT_VIRTUAL_VIEWPORT_HEIGHT,
  );
  const safeOverscan = Math.max(0, Math.floor(overscan));

  const firstVisible = findIndexAtOffset(layout.offsets, safeScrollTop);
  const lastVisible = findIndexAtOffset(layout.offsets, safeScrollTop + safeViewport);

  const startIndex = Math.max(0, firstVisible - safeOverscan);
  const endIndex = Math.min(count, lastVisible + safeOverscan + 1);
  const topSpacerHeight = layout.offsets[startIndex];
  const bottomSpacerHeight = Math.max(0, totalHeight - layout.offsets[endIndex]);

  return {
    startIndex,
    endIndex,
    topSpacerHeight,
    bottomSpacerHeight,
    totalHeight,
  };
}

export interface TimelineSegmentLike {
  id: number;
  start: number;
  end: number;
  speaker?: string;
  flagged?: boolean;
  overflow?: boolean;
  semantic_flag?: boolean;
  review_status?: string;
}

export interface TimelineBucket {
  key: string;
  bucketed: boolean;
  leftPct: number;
  widthPct: number;
  representativeSegmentId: number;
  representativeStart: number;
  firstSegmentId: number;
  lastSegmentId: number;
  segmentCount: number;
  speaker: string;
  hasActive: boolean;
  hasFlagged: boolean;
}

function isSegmentFlagged(seg: TimelineSegmentLike): boolean {
  return Boolean(
    seg.flagged ||
    seg.overflow ||
    seg.semantic_flag ||
    seg.review_status === 'needs_review',
  );
}

/**
 * Convert an arbitrary number of segments into a bounded list of scrub-bar
 * markers (`<= maxBuckets`). Small jobs (`<= maxBuckets`) keep exact 1-to-1
 * segment markers; 6h-12h jobs with 6k-12k+ segments aggregate into uniform
 * buckets while preserving active/flagged priority and click-to-seek targets.
 */
export function buildTimelineBuckets(
  segments: readonly TimelineSegmentLike[],
  timelineStart: number,
  totalDuration: number | null,
  activeSegmentId: number | null | undefined,
  maxBuckets = DEFAULT_MAX_TIMELINE_BUCKETS,
): TimelineBucket[] {
  if (
    totalDuration === null ||
    !Number.isFinite(totalDuration) ||
    totalDuration <= 0 ||
    segments.length === 0
  ) {
    return [];
  }

  const timelineEnd = timelineStart + totalDuration;
  const safeMaxBuckets = Math.max(1, Math.floor(maxBuckets));

  if (segments.length <= safeMaxBuckets) {
    const markers: TimelineBucket[] = [];
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      const clippedStart = Math.max(seg.start, timelineStart);
      const clippedEnd = Math.min(seg.end, timelineEnd);
      if (clippedEnd <= clippedStart) continue;
      const leftPct = ((clippedStart - timelineStart) / totalDuration) * 100;
      const widthPct = ((clippedEnd - clippedStart) / totalDuration) * 100;
      markers.push({
        key: `seg-${seg.id}`,
        bucketed: false,
        leftPct,
        widthPct,
        representativeSegmentId: seg.id,
        representativeStart: seg.start,
        firstSegmentId: seg.id,
        lastSegmentId: seg.id,
        segmentCount: 1,
        speaker: seg.speaker || 'SPEAKER_00',
        hasActive: seg.id === activeSegmentId,
        hasFlagged: isSegmentFlagged(seg),
      });
    }
    return markers;
  }

  interface MutableBucket {
    index: number;
    firstSegmentId: number;
    lastSegmentId: number;
    segmentCount: number;
    speaker: string;
    representativeSegmentId: number;
    representativeStart: number;
    hasActive: boolean;
    hasFlagged: boolean;
  }

  const buckets = new Array<MutableBucket | undefined>(safeMaxBuckets);
  const bucketWidthPct = 100 / safeMaxBuckets;

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    const clippedStart = Math.max(seg.start, timelineStart);
    const clippedEnd = Math.min(seg.end, timelineEnd);
    if (clippedEnd <= clippedStart) continue;

    const startRatio = (clippedStart - timelineStart) / totalDuration;
    const endRatio = (clippedEnd - timelineStart) / totalDuration;
    const startIdx = Math.min(safeMaxBuckets - 1, Math.max(0, Math.floor(startRatio * safeMaxBuckets)));
    const endIdx = Math.min(
      safeMaxBuckets - 1,
      Math.max(startIdx, Math.floor(Math.max(0, endRatio - 1e-9) * safeMaxBuckets)),
    );
    const segActive = seg.id === activeSegmentId;
    const segFlagged = isSegmentFlagged(seg);

    for (let b = startIdx; b <= endIdx; b++) {
      const existing = buckets[b];
      if (!existing) {
        buckets[b] = {
          index: b,
          firstSegmentId: seg.id,
          lastSegmentId: seg.id,
          segmentCount: 1,
          speaker: seg.speaker || 'SPEAKER_00',
          representativeSegmentId: seg.id,
          representativeStart: seg.start,
          hasActive: segActive,
          hasFlagged: segFlagged,
        };
      } else {
        existing.lastSegmentId = seg.id;
        existing.segmentCount += 1;
        if (segActive) {
          existing.hasActive = true;
          existing.representativeSegmentId = seg.id;
          existing.representativeStart = seg.start;
          existing.speaker = seg.speaker || existing.speaker;
        } else if (segFlagged && !existing.hasFlagged && !existing.hasActive) {
          existing.hasFlagged = true;
          existing.representativeSegmentId = seg.id;
          existing.representativeStart = seg.start;
          existing.speaker = seg.speaker || existing.speaker;
        } else if (segFlagged) {
          existing.hasFlagged = true;
        }
      }
    }
  }

  const result: TimelineBucket[] = [];
  for (let b = 0; b < safeMaxBuckets; b++) {
    const entry = buckets[b];
    if (!entry) continue;
    result.push({
      key: `bucket-${b}`,
      bucketed: true,
      leftPct: b * bucketWidthPct,
      widthPct: bucketWidthPct,
      representativeSegmentId: entry.representativeSegmentId,
      representativeStart: entry.representativeStart,
      firstSegmentId: entry.firstSegmentId,
      lastSegmentId: entry.lastSegmentId,
      segmentCount: entry.segmentCount,
      speaker: entry.speaker,
      hasActive: entry.hasActive,
      hasFlagged: entry.hasFlagged,
    });
  }
  return result;
}
