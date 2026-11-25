import React, { useRef, useEffect, useState } from 'react';
import { useJob } from '@/context/JobContext';
import { useTranslation } from '@/context/I18nContext';
import { fetchJobWaveform } from '@/lib/api';
import { formatSeconds } from '@/lib/utils';
import { positiveFinite } from '@/lib/telemetry';
import { Headphones, Volume2, Mic, Music } from 'lucide-react';

const WAVEFORM_BAR_COUNT = 64;

export const WaveformPlayer: React.FC = () => {
  const { activeJob, segments, activeSegmentIndex, selectedAudioTrack, setSelectedAudioTrack, isPlaying, currentTime } = useJob();
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [peaks, setPeaks] = useState<number[]>([]);
  const [waveformDuration, setWaveformDuration] = useState<number | null>(null);
  const [samplingMode, setSamplingMode] = useState<string>('');
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('unavailable');

  const activeSegment = segments[activeSegmentIndex] || segments[0];

  const audioSrc = activeJob
    ? (selectedAudioTrack === 'a'
      ? `/work/${encodeURIComponent(activeJob.id)}/vocals.wav`
      : selectedAudioTrack === 'b'
        ? `/work/${encodeURIComponent(activeJob.id)}/voice_track.wav`
        : `/work/${encodeURIComponent(activeJob.id)}/accompaniment.wav`)
    : null;

  const trackLabel = selectedAudioTrack === 'a'
    ? t('monitor.track_a')
    : selectedAudioTrack === 'b'
      ? t('monitor.track_b')
      : t('monitor.track_bgm');

  // Request bounded server-computed peaks instead of fetching and decoding full WAV files
  // into browser RAM (a near-12h 48kHz WAV is 4-8 GiB and OOMs AudioContext.decodeAudioData).
  useEffect(() => {
    if (!activeJob?.id) {
      setPeaks([]);
      setWaveformDuration(null);
      setSamplingMode('');
      setStatus('unavailable');
      return;
    }

    const controller = new AbortController();
    setStatus('loading');
    setPeaks([]);
    setWaveformDuration(null);
    setSamplingMode('');

    const loadBoundedPeaks = async () => {
      try {
        const data = await fetchJobWaveform(
          activeJob.id,
          selectedAudioTrack,
          WAVEFORM_BAR_COUNT,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (!data || !Array.isArray(data.peaks) || data.peaks.length === 0) {
          setPeaks([]);
          setWaveformDuration(null);
          setSamplingMode('');
          setStatus('unavailable');
          return;
        }
        setPeaks(data.peaks);
        setWaveformDuration(positiveFinite(data.duration_seconds) ? data.duration_seconds : null);
        setSamplingMode(data.sampling_mode || '');
        setStatus('ready');
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error('Failed loading bounded waveform peaks:', err);
        setPeaks([]);
        setWaveformDuration(null);
        setSamplingMode('');
        setStatus('unavailable');
      }
    };

    void loadBoundedPeaks();
    return () => {
      controller.abort();
    };
  }, [activeJob?.id, selectedAudioTrack]);

  useEffect(() => {
    if (audioRef.current) {
      if (Math.abs(audioRef.current.currentTime - currentTime) > 0.5) {
        audioRef.current.currentTime = currentTime;
      }
    }
  }, [currentTime]);

  useEffect(() => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.play().catch(e => console.error(e));
      } else {
        audioRef.current.pause();
      }
    }
  }, [isPlaying, audioSrc]);

  // Redraw waveform reactively on state/time changes instead of spinning a 60fps idle rAF loop.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const width = canvas.width;
    const height = canvas.height;
    const centerY = height / 2;

    let primaryColor = '#0284c7'; // B: Sky / Cyan
    if (selectedAudioTrack === 'a') primaryColor = '#ea580c'; // A: Orange
    if (selectedAudioTrack === 'bgm') primaryColor = '#8b5cf6'; // BGM: Purple

    if (status !== 'ready' || peaks.length === 0) {
      ctx.fillStyle = '#334155';
      ctx.fillRect(0, centerY - 1, width, 2);
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(
        status === 'loading' ? t('monitor.waveform_loading') : t('monitor.waveform_unavailable'),
        width / 2,
        centerY + 4,
      );
      return;
    }

    const barCount = peaks.length;
    const barWidth = Math.max(1, width / barCount - 1.5);

    for (let i = 0; i < barCount; i++) {
      const amplitude = peaks[i] || 0;
      const barHeight = Math.max(2, amplitude * height * 0.9);
      const x = i * (barWidth + 1.5);
      const y = centerY - barHeight / 2;

      ctx.fillStyle = primaryColor;
      ctx.beginPath();
      ctx.roundRect(x, y, barWidth, barHeight, 2);
      ctx.fill();
    }

    const audioDuration = audioRef.current?.duration;
    const persistedDuration = activeJob?.result?.duration_seconds;
    const duration = positiveFinite(audioDuration)
      ? audioDuration
      : positiveFinite(waveformDuration)
        ? waveformDuration
        : positiveFinite(persistedDuration)
          ? persistedDuration
          : null;
    if (duration !== null && currentTime !== undefined) {
      const playheadX = Math.max(0, Math.min(width - 2, (currentTime / duration) * width));
      ctx.fillStyle = '#ef4444';
      ctx.fillRect(playheadX, 0, 2, height);
    }
  }, [selectedAudioTrack, peaks, status, currentTime, waveformDuration, activeJob, t]);

  return (
    <div className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl p-3 shadow-sm space-y-2.5 font-mono shrink-0 select-none">
      <audio ref={audioRef} src={audioSrc || undefined} preload="none" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Headphones className="w-4 h-4 text-sky-500" />
          <h3 className="text-xs font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wide">
            {t('monitor.ab_audition')}
          </h3>
        </div>

        {/* Active Segment Timecode Pill */}
        {activeSegment && (
          <span className="text-xs text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/60 px-2 py-0.5 rounded font-mono font-medium">
            SEG #{activeSegment.id} // {formatSeconds(activeSegment.start)} - {formatSeconds(activeSegment.end)}
          </span>
        )}
      </div>

      {/* A/B/BGM Track Switcher */}
      <div className="grid grid-cols-3 gap-1.5 p-1 bg-slate-100 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800/80 rounded-lg text-xs">
        <button
          onClick={() => setSelectedAudioTrack('a')}
          className={`flex items-center justify-center gap-1.5 h-8 px-2 rounded-md transition-all font-semibold whitespace-nowrap cursor-pointer ${
            selectedAudioTrack === 'a'
              ? 'bg-orange-600 text-white shadow-xs'
              : 'text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-200/60 dark:hover:bg-slate-800/60'
          }`}
          title={t('monitor.track_a')}
        >
          <Mic className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{t('monitor.track_a')}</span>
        </button>

        <button
          onClick={() => setSelectedAudioTrack('b')}
          className={`flex items-center justify-center gap-1.5 h-8 px-2 rounded-md transition-all font-semibold whitespace-nowrap cursor-pointer ${
            selectedAudioTrack === 'b'
              ? 'bg-sky-700 text-white shadow-xs'
              : 'text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-200/60 dark:hover:bg-slate-800/60'
          }`}
          title={t('monitor.track_b')}
        >
          <Volume2 className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{t('monitor.track_b')}</span>
        </button>

        <button
          onClick={() => setSelectedAudioTrack('bgm')}
          className={`flex items-center justify-center gap-1.5 h-8 px-2 rounded-md transition-all font-semibold whitespace-nowrap cursor-pointer ${
            selectedAudioTrack === 'bgm'
              ? 'bg-purple-600 text-white shadow-xs'
              : 'text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-200/60 dark:hover:bg-slate-800/60'
          }`}
          title={t('monitor.track_bgm')}
        >
          <Music className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{t('monitor.track_bgm')}</span>
        </button>
      </div>

      {/* Waveform Canvas */}
      <div className="relative h-10 bg-slate-950 rounded-lg px-2 py-1 flex items-center justify-center overflow-hidden border border-slate-300/80 dark:border-slate-800">
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={t('monitor.waveform_aria', { track: trackLabel })}
          data-waveform-status={status}
          data-waveform-mode={samplingMode || 'none'}
          data-waveform-bars={peaks.length}
          className="w-full h-full"
        />

        {/* Level lines */}
        <div className="absolute inset-x-0 top-1/2 h-px bg-slate-800 pointer-events-none" />
        <span className="absolute right-2 top-0.5 text-[9px] font-mono text-slate-400 font-semibold">
          -14 LUFS TARGET
        </span>
      </div>
    </div>
  );
};
