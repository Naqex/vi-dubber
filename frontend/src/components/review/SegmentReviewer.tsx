import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useJob } from '@/context/JobContext';
import { useTranslation } from '@/context/I18nContext';
import { SegmentFilterBar, FilterType } from './SegmentFilterBar';
import { SegmentCard } from './SegmentCard';
import { CheckCircle2, SlidersHorizontal, Keyboard, X, CheckCheck, Download, FileText } from 'lucide-react';
import { isFinalJobReady } from '@/lib/utils';
import {
  buildVirtualLayout,
  computeVirtualWindow,
  DEFAULT_VIRTUAL_OVERSCAN,
  DEFAULT_VIRTUAL_ROW_HEIGHT,
  DEFAULT_VIRTUAL_VIEWPORT_HEIGHT,
} from '@/lib/virtualList';

export const SegmentReviewer: React.FC = () => {
  const {
    previewPlaybackBlockedJobId,
    activeJob,
    segments,
    activeSegmentIndex,
    setActiveSegmentIndex,
    requestSeek,
    isPlaying,
    setIsPlaying,
    updateSegment,
    acceptSegment,
    acceptAllSegments,
    rerenderSegment,
    reviewMutations,
    retrySegmentMutation,
  } = useJob();
  const { t } = useTranslation();

  const [currentFilter, setCurrentFilter] = useState<FilterType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showHotkeysGuide, setShowHotkeysGuide] = useState(false);
  const [isAcceptingAll, setIsAcceptingAll] = useState(false);
  const [acceptAllError, setAcceptAllError] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(DEFAULT_VIRTUAL_VIEWPORT_HEIGHT);
  const [measurementVersion, setMeasurementVersion] = useState(0);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const measuredHeightsRef = useRef<Map<number, number>>(new Map());
  const rowObserversRef = useRef<Map<number, ResizeObserver>>(new Map());
  const lastScrolledActiveIdRef = useRef<number | null>(null);

  // Map segment id -> index in `segments` in O(N) once so click/hotkey jumps are O(1)
  const segmentIndexById = useMemo(() => {
    const map = new Map<number, number>();
    for (let i = 0; i < segments.length; i++) {
      map.set(segments[i].id, i);
    }
    return map;
  }, [segments]);

  // Calculate all filter counts in a single O(N) pass
  const counts = useMemo(() => {
    let flagged = 0;
    let needs_review = 0;
    let accepted = 0;
    let overflow = 0;
    let multispeaker = 0;
    for (let i = 0; i < segments.length; i++) {
      const s = segments[i];
      if (s.flagged || s.overflow || s.semantic_flag) flagged += 1;
      if (s.review_status === 'needs_review') needs_review += 1;
      if (s.review_status === 'accepted') accepted += 1;
      if (s.overflow) overflow += 1;
      if (s.multi_speaker || s.speaker_overlap) multispeaker += 1;
    }
    return {
      all: segments.length,
      flagged,
      needs_review,
      accepted,
      overflow,
      multispeaker,
    };
  }, [segments]);

  // Filter and search segments
  const filteredSegments = useMemo(() => {
    const trimmedQuery = searchQuery.trim().toLowerCase();
    return segments.filter(seg => {
      // Filter criteria
      if (currentFilter === 'flagged' && !seg.flagged && !seg.overflow && !seg.semantic_flag) return false;
      if (currentFilter === 'needs_review' && seg.review_status !== 'needs_review') return false;
      if (currentFilter === 'accepted' && seg.review_status !== 'accepted') return false;
      if (currentFilter === 'overflow' && !seg.overflow) return false;
      if (currentFilter === 'multispeaker' && !seg.multi_speaker && !seg.speaker_overlap) return false;

      // Search query
      if (trimmedQuery) {
        const matchesEn = seg.text.toLowerCase().includes(trimmedQuery);
        const matchesVi = seg.vi.toLowerCase().includes(trimmedQuery);
        const matchesSpk = seg.speaker.toLowerCase().includes(trimmedQuery);
        const matchesId = seg.id.toString() === trimmedQuery;
        if (!matchesEn && !matchesVi && !matchesSpk && !matchesId) return false;
      }

      return true;
    });
  }, [segments, currentFilter, searchQuery]);

  const filteredIndexById = useMemo(() => {
    const map = new Map<number, number>();
    for (let i = 0; i < filteredSegments.length; i++) {
      map.set(filteredSegments[i].id, i);
    }
    return map;
  }, [filteredSegments]);

  const virtualLayout = useMemo(
    () => buildVirtualLayout(filteredSegments, measuredHeightsRef.current, DEFAULT_VIRTUAL_ROW_HEIGHT),
    // measurementVersion bumps when ResizeObserver records a height delta
    [filteredSegments, measurementVersion],
  );

  const virtualWindow = useMemo(
    () => computeVirtualWindow(virtualLayout, scrollTop, viewportHeight, DEFAULT_VIRTUAL_OVERSCAN),
    [virtualLayout, scrollTop, viewportHeight],
  );

  const visibleSegmentsSlice = useMemo(
    () => filteredSegments.slice(virtualWindow.startIndex, virtualWindow.endIndex),
    [filteredSegments, virtualWindow.startIndex, virtualWindow.endIndex],
  );

  const acceptedCount = counts.accepted;
  const hasPendingMutation = Object.values(reviewMutations).some(state => state.status === 'pending');

  // Reset cached row measurements when switching jobs
  useEffect(() => {
    measuredHeightsRef.current.clear();
    rowObserversRef.current.forEach(observer => observer.disconnect());
    rowObserversRef.current.clear();
    lastScrolledActiveIdRef.current = null;
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
    setScrollTop(0);
    setMeasurementVersion(v => v + 1);
  }, [activeJob?.id]);

  // Reset scroll offset to top when filter or search query narrows the list
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
    setScrollTop(0);
  }, [currentFilter, searchQuery]);

  // Track scroll container viewport height
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const syncViewportHeight = () => {
      const nextHeight = container.clientHeight;
      if (nextHeight > 0) {
        setViewportHeight(prev => (Math.abs(prev - nextHeight) > 1 ? nextHeight : prev));
      }
    };
    syncViewportHeight();

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(syncViewportHeight);
      observer.observe(container);
      return () => observer.disconnect();
    }
    window.addEventListener('resize', syncViewportHeight);
    return () => window.removeEventListener('resize', syncViewportHeight);
  }, []);

  // Cleanup any row observers on unmount
  useEffect(() => {
    return () => {
      rowObserversRef.current.forEach(observer => observer.disconnect());
      rowObserversRef.current.clear();
    };
  }, []);

  const handleListScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const nextTop = event.currentTarget.scrollTop;
    setScrollTop(prev => (Math.abs(prev - nextTop) >= 1 ? nextTop : prev));
  }, []);

  const registerRowRef = useCallback((segmentId: number, el: HTMLDivElement | null) => {
    cardRefs.current[segmentId] = el;
    const prevObserver = rowObserversRef.current.get(segmentId);
    if (prevObserver) {
      prevObserver.disconnect();
      rowObserversRef.current.delete(segmentId);
    }
    if (!el) return;

    const recordHeight = () => {
      const rectHeight = Math.ceil(el.getBoundingClientRect().height);
      if (rectHeight <= 0) return;
      const previous = measuredHeightsRef.current.get(segmentId);
      if (previous === undefined || Math.abs(previous - rectHeight) > 2) {
        measuredHeightsRef.current.set(segmentId, rectHeight);
        setMeasurementVersion(v => v + 1);
      }
    };
    recordHeight();

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(recordHeight);
      observer.observe(el);
      rowObserversRef.current.set(segmentId, observer);
    }
  }, []);

  // Auto-scroll active card into view (works even when the active segment is off-screen in a 10k+ list)
  const activeSegmentId = segments[activeSegmentIndex]?.id ?? null;
  useEffect(() => {
    if (activeSegmentId === null) return;
    if (lastScrolledActiveIdRef.current === activeSegmentId) return;
    lastScrolledActiveIdRef.current = activeSegmentId;

    const filteredIdx = filteredIndexById.get(activeSegmentId);
    if (filteredIdx === undefined) return;

    const container = scrollContainerRef.current;
    if (!container) return;

    const itemTop = virtualLayout.offsets[filteredIdx];
    const itemBottom = virtualLayout.offsets[filteredIdx + 1];
    const currentTop = container.scrollTop;
    const effectiveHeight = container.clientHeight > 0 ? container.clientHeight : viewportHeight;

    if (itemTop < currentTop || itemBottom > currentTop + effectiveHeight) {
      const targetTop = Math.max(0, Math.round(itemTop - effectiveHeight * 0.25));
      container.scrollTop = targetTop;
      setScrollTop(targetTop);
    }
  }, [activeSegmentId, filteredIndexById, virtualLayout, viewportHeight]);

  // Global Keyboard Hotkeys Engine
  useEffect(() => {
    const handleGlobalKeyDown = async (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isTyping =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable ||
          target.tagName === 'SELECT');

      // 1. Space: Toggle playback when not typing
      if (e.key === ' ' && !isTyping) {
        e.preventDefault();
        if (previewPlaybackBlockedJobId !== activeJob?.id) setIsPlaying(!isPlaying);
        return;
      }

      // 2. Navigation: ArrowDown or 'j' when not typing
      if (!isTyping && (e.key === 'ArrowDown' || e.key === 'j')) {
        e.preventDefault();
        if (activeSegmentIndex < segments.length - 1) {
          const nextIdx = activeSegmentIndex + 1;
          setActiveSegmentIndex(nextIdx);
          requestSeek(segments[nextIdx].start);
        }
        return;
      }

      // 3. Navigation: ArrowUp or 'k' when not typing
      if (!isTyping && (e.key === 'ArrowUp' || e.key === 'k')) {
        e.preventDefault();
        if (activeSegmentIndex > 0) {
          const prevIdx = activeSegmentIndex - 1;
          setActiveSegmentIndex(prevIdx);
          requestSeek(segments[prevIdx].start);
        }
        return;
      }

      // 4. Ctrl + Enter: Accept currently active segment and advance (if not captured by textarea)
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (!target || target.tagName !== 'TEXTAREA') {
          e.preventDefault();
          const activeSeg = segments[activeSegmentIndex];
          if (activeSeg) {
            try {
              await acceptSegment(activeSeg.id);
            } catch {
              // The card receives the mutation error and exposes the retry action.
              return;
            }
            if (activeSegmentIndex < segments.length - 1) {
              const nextIdx = activeSegmentIndex + 1;
              setActiveSegmentIndex(nextIdx);
              requestSeek(segments[nextIdx].start);
            }
          }
        }
        return;
      }

      // 5. Ctrl + S: Prevent browser save dialog
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [
    previewPlaybackBlockedJobId,
    activeJob?.id,
    isPlaying,
    activeSegmentIndex,
    segments,
    setIsPlaying,
    setActiveSegmentIndex,
    requestSeek,
    acceptSegment,
  ]);

  // Handle Ctrl+Enter from inside a segment card's textarea
  const handleCtrlEnterFromCard = async (id: number, text: string, speaker: string) => {
    // 1. Save and accept
    await updateSegment(id, { vi: text, speaker, review_status: 'accepted' });
    // 2. Advance to next segment
    const curIdx = segmentIndexById.get(id) ?? -1;
    if (curIdx !== -1 && curIdx < segments.length - 1) {
      const nextIdx = curIdx + 1;
      setActiveSegmentIndex(nextIdx);
      requestSeek(segments[nextIdx].start);
    }
  };

  const handleAcceptAll = async () => {
    setIsAcceptingAll(true);
    setAcceptAllError(null);
    try {
      await acceptAllSegments();
    } catch (error) {
      setAcceptAllError(error instanceof Error && error.message ? error.message : 'Request failed');
    } finally {
      setIsAcceptingAll(false);
    }
  };

  return (
    <div className="h-full overflow-hidden flex flex-col bg-white dark:bg-slate-900/80 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm select-none">
      {/* Right Column Header */}
      <div className="p-2.5 border-b border-slate-200 dark:border-slate-800 space-y-2.5 shrink-0 bg-slate-50/50 dark:bg-slate-950/30">
        {/* Top Info Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4 text-orange-500 shrink-0" />
            <h3 className="text-xs font-bold font-mono text-slate-900 dark:text-slate-100 uppercase tracking-wide">
              {t('review.title')}
            </h3>
            <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
              {segments.length} TOTAL
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Accepted Progress Badge */}
            <div className="flex items-center gap-1.5 text-xs font-mono hidden xl:flex">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              <span className="text-slate-600 dark:text-slate-300">
                {t('review.approved')}: <strong className="text-emerald-600 dark:text-emerald-400">{acceptedCount}</strong> / {segments.length}
              </span>
            </div>

            {/* Duyệt tất cả (Batch Approve) */}
            <button
              onClick={handleAcceptAll}
              disabled={isAcceptingAll || hasPendingMutation || acceptedCount === segments.length}
              className={`flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-mono font-semibold transition cursor-pointer ${
                acceptedCount === segments.length
                  ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 border border-slate-200 dark:border-slate-800 cursor-default'
                  : 'bg-emerald-700 hover:bg-emerald-800 text-white shadow-xs'
              }`}
              title={t('review.accept_all')}
            >
              <CheckCheck className="w-3.5 h-3.5" />
              <span>{isAcceptingAll ? t('review.accepting') : `${t('review.accept_all')} (${segments.length})`}</span>
            </button>

            {/* Tải Video & Phụ đề khi hoàn tất */}
            {isFinalJobReady(activeJob) && (
              <div className="flex items-center gap-1">
                <a
                  href={`/api/jobs/${activeJob.id}/download`}
                  download
                  className="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-mono font-semibold bg-emerald-700 hover:bg-emerald-800 text-white shadow-xs transition cursor-pointer"
                  title={t('common.download_video')}
                  aria-label={t('common.download_video')}
                >
                  <Download className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{t('common.download_video')}</span>
                </a>
                <a
                  href={`/api/jobs/${activeJob.id}/download?type=subtitles`}
                  download
                  className="flex items-center gap-1 h-7 px-2 rounded-lg text-xs font-mono font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 transition cursor-pointer"
                  title={t('common.download_subtitles')}
                  aria-label={t('common.download_subtitles')}
                >
                  <FileText className="w-3.5 h-3.5 text-sky-500" />
                  <span className="text-[11px]">SRT</span>
                </a>
              </div>
            )}

            {/* Hotkeys Guide Chip */}
            <div className="relative">
              <button
                onClick={() => setShowHotkeysGuide(!showHotkeysGuide)}
                className="flex items-center gap-1.5 h-7 px-2 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 text-xs font-mono transition cursor-pointer"
                title={t('hotkeys.title')}
              >
                <Keyboard className="w-3.5 h-3.5 text-orange-500 shrink-0" />
                <span className="font-semibold hidden sm:inline">{t('hotkeys.title')}</span>
              </button>

              {/* Hotkeys Floating Tooltip / Drawer */}
              {showHotkeysGuide && (
                <div className="absolute right-0 mt-1 w-80 p-3 bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-700 text-xs font-mono z-50 animate-in fade-in zoom-in-95 duration-150">
                  <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 pb-2 mb-2 font-bold text-slate-900 dark:text-slate-100">
                    <span className="flex items-center gap-1.5">
                      <Keyboard className="w-4 h-4 text-orange-500" />
                      {t('hotkeys.title')}
                    </span>
                    <button
                      onClick={() => setShowHotkeysGuide(false)}
                      className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition cursor-pointer"
                      title={t('common.close')}
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="space-y-1.5 text-[11px]">
                    <div className="flex justify-between items-center py-0.5">
                      <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 rounded font-bold text-slate-700 dark:text-slate-300">Space</span>
                      <span className="text-slate-600 dark:text-slate-300">{t('hotkeys.play_pause')}</span>
                    </div>
                    <div className="flex justify-between items-center py-0.5">
                      <span className="px-1.5 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded font-bold border border-emerald-500/30">Ctrl + Enter</span>
                      <span className="text-slate-600 dark:text-slate-300">{t('hotkeys.save_accept_next')}</span>
                    </div>
                    <div className="flex justify-between items-center py-0.5">
                      <span className="px-1.5 py-0.5 bg-orange-500/10 text-orange-600 dark:text-orange-400 rounded font-bold border border-orange-500/30">Ctrl + S</span>
                      <span className="text-slate-600 dark:text-slate-300">{t('hotkeys.save_edit')}</span>
                    </div>
                    <div className="flex justify-between items-center py-0.5">
                      <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 rounded font-bold text-slate-700 dark:text-slate-300">↓ / j</span>
                      <span className="text-slate-600 dark:text-slate-300">{t('hotkeys.next_segment')}</span>
                    </div>
                    <div className="flex justify-between items-center py-0.5">
                      <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 rounded font-bold text-slate-700 dark:text-slate-300">↑ / k</span>
                      <span className="text-slate-600 dark:text-slate-300">{t('hotkeys.prev_segment')}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <SegmentFilterBar
          currentFilter={currentFilter}
          onSelectFilter={setCurrentFilter}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          counts={counts}
        />
        {acceptAllError && (
          <div
            role="alert"
            className="flex items-center justify-between gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-[11px] font-mono text-rose-700 dark:text-rose-300"
          >
            <span>Accept all failed: {acceptAllError}</span>
            <button
              type="button"
              onClick={handleAcceptAll}
              disabled={isAcceptingAll}
              className="shrink-0 rounded border border-rose-500/40 px-2 py-0.5 font-semibold hover:bg-rose-500/10 disabled:opacity-50"
            >
              Retry
            </button>
          </div>
        )}
      </div>

      {/* Body: Windowed/virtualized scrollable list of segment cards */}
      <div
        ref={scrollContainerRef}
        onScroll={handleListScroll}
        tabIndex={0}
        aria-label={t('review.title')}
        data-virtualized-list="true"
        data-total-segments={filteredSegments.length}
        data-rendered-segments={visibleSegmentsSlice.length}
        className="flex-1 min-h-0 overflow-y-auto p-2"
      >
        {filteredSegments.length === 0 ? (
          <div className="text-center py-16 text-slate-500 dark:text-slate-400 font-mono text-xs">
            {t('review.no_results')}
          </div>
        ) : (
          <div>
            {virtualWindow.topSpacerHeight > 0 && (
              <div
                aria-hidden="true"
                data-virtual-spacer="top"
                style={{ height: `${virtualWindow.topSpacerHeight}px` }}
              />
            )}
            {visibleSegmentsSlice.map(seg => (
              <div
                key={seg.id}
                data-segment-card="true"
                data-segment-id={seg.id}
                className="pb-2"
                ref={el => registerRowRef(seg.id, el)}
              >
                <SegmentCard
                  segment={seg}
                  mutation={reviewMutations[seg.id]}
                  onRetry={() => retrySegmentMutation(seg.id)}
                  isActive={seg.id === activeSegmentId}
                  onSelect={() => {
                    const idx = segmentIndexById.get(seg.id);
                    if (idx !== undefined) {
                      setActiveSegmentIndex(idx);
                      requestSeek(seg.start);
                    }
                  }}
                  onSave={async (id, text, speaker) => {
                    await updateSegment(id, { vi: text, speaker, review_status: 'reviewed' });
                  }}
                  onAccept={async (id) => {
                    await acceptSegment(id);
                  }}
                  onRerender={async (id) => {
                    await rerenderSegment(id);
                  }}
                  onCtrlEnter={handleCtrlEnterFromCard}
                />
              </div>
            ))}
            {virtualWindow.bottomSpacerHeight > 0 && (
              <div
                aria-hidden="true"
                data-virtual-spacer="bottom"
                style={{ height: `${virtualWindow.bottomSpacerHeight}px` }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
};
