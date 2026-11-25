import React, { useState, useEffect } from 'react';
import { useJob } from '@/context/JobContext';
import { useTranslation } from '@/context/I18nContext';
import {
  formatSeconds,
  resolveActiveStageIndex,
  PIPELINE_STAGES,
} from '@/lib/utils';
import { deriveEtaTelemetry, finiteNumber, resolveCompletedQaState } from '@/lib/telemetry';
import { StageDefinition } from '@/types';
import { StageDetailModal } from '@/components/pipeline/StageDetailModal';
import {
  Wifi,
  Radio,
  Play,
  Pause,
  Square,
  CheckCircle2,
  AlertTriangle,
  Timer,
  Clock,
} from 'lucide-react';

export const SystemBar: React.FC = () => {
  const { activeJob, systemStatus, controlJob } = useJob();
  const { language, t } = useTranslation();

  const [liveElapsed, setLiveElapsed] = useState<number | null>(null);
  const [selectedStage, setSelectedStage] = useState<StageDefinition | null>(null);

  const isJobComplete = activeJob?.status === 'completed';
  const isJobFailed = activeJob?.status === 'failed';
  const isJobCancelled = activeJob?.status === 'cancelled';
  const completedQaState = resolveCompletedQaState(activeJob);
  const isWebSocketLive =
    systemStatus.websocket_connected === true &&
    systemStatus.transport_mode === 'websocket';
  const persistedElapsed = activeJob?.result?.elapsed_seconds ?? activeJob?.metrics?.total_wall_seconds;

  useEffect(() => {
    if (!activeJob || !finiteNumber(persistedElapsed) || persistedElapsed < 0) {
      setLiveElapsed(null);
      return;
    }
    setLiveElapsed(persistedElapsed);

    if (activeJob.status === 'running' && persistedElapsed >= 0) {
      const timer = setInterval(() => {
        setLiveElapsed(prev => (prev === null ? prev : prev + 1));
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [activeJob, persistedElapsed]);

  const eta = deriveEtaTelemetry({
    status: activeJob?.status,
    progress: activeJob?.progress,
    elapsedSeconds: liveElapsed,
    durationSeconds: activeJob?.result?.duration_seconds,
    realTimeFactor: activeJob?.result?.real_time_factor,
  });
  const progress = eta.progress;

  const activeIndex = activeJob && activeJob.stage && progress !== null
    ? resolveActiveStageIndex(activeJob.stage, progress)
    : -1;

  const activeStage = activeIndex >= 0 ? PIPELINE_STAGES[activeIndex] ?? null : null;
  const stageName = activeStage ? (language === 'vi' ? activeStage.labelVi : activeStage.labelEn) : '';
  const unavailable = t('common.unavailable');
  const openStageDetails = () => setSelectedStage(activeStage);
  const handleProgressKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if ((event.key === 'Enter' || event.key === ' ') && activeStage) {
      event.preventDefault();
      openStageDetails();
    }
  };

  return (
    <div className="min-h-[36px] shrink-0 bg-white dark:bg-[#090d16] border-b border-slate-200 dark:border-slate-800 px-3 py-2 lg:py-0 flex flex-wrap lg:flex-nowrap items-center justify-between text-xs font-mono select-none gap-x-4 gap-y-2 w-full">
      {/* Section 1: Progress bar with stage label */}
      <div className="flex w-full min-w-0 items-center gap-3 lg:w-auto lg:flex-1 lg:max-w-xl">
        <button
          onClick={() => setSelectedStage(activeStage)}
          className="min-w-0 flex-1 lg:flex-none text-left font-bold text-slate-800 dark:text-slate-200 hover:text-orange-500 dark:hover:text-orange-400 transition cursor-pointer whitespace-normal lg:whitespace-nowrap"
          title={language === 'vi' ? 'Xem chi tiết bước xử lý' : 'Click to view stage details'}
        >
          {activeStage ? t('system.stage_of', { current: activeIndex + 1, total: 7 }) : unavailable}: {stageName || unavailable} · {progress === null ? unavailable : `${Math.round(progress * 100)}%`}
        </button>
        <div
          className="w-20 shrink-0 lg:w-auto lg:flex-1 h-1.5 bg-slate-200 dark:bg-slate-800 rounded-full relative mx-2 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/60"
          role="button"
          tabIndex={activeStage ? 0 : -1}
          aria-label={activeStage ? (language === 'vi' ? 'Mở chi tiết bước xử lý' : 'Open stage details') : unavailable}
          aria-disabled={!activeStage}
          onClick={openStageDetails}
          onKeyDown={handleProgressKeyDown}
        >
          {/* 7 stage marker dots */}
          {PIPELINE_STAGES.map((_, i) => (
            <div key={i}
              className={`absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full ${i < activeIndex ? 'bg-emerald-500' : i === activeIndex ? 'bg-orange-500 ring-2 ring-orange-500/30' : 'bg-slate-300 dark:bg-slate-700'}`}
              style={{ left: `${(i / 6) * 100}%` }}
            />
          ))}
          {/* Progress fill */}
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isJobComplete
                ? completedQaState === 'failed'
                  ? 'bg-rose-500'
                  : completedQaState === 'unverified'
                    ? 'bg-amber-500'
                    : 'bg-emerald-500'
                : isJobFailed
                  ? 'bg-rose-500'
                  : isJobCancelled
                    ? 'bg-slate-400 dark:bg-slate-600'
                    : 'bg-orange-500'
            }`}
            style={{ width: progress === null ? '0%' : `${progress * 100}%` }}
          />
        </div>
      </div>

      {/* Section 2: ETA Timer */}
      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-1 text-slate-600 dark:text-slate-300">
          <Timer className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
          <span className="text-slate-800 dark:text-slate-100 font-bold tabular-nums">
            {eta.elapsedSeconds === null ? unavailable : formatSeconds(eta.elapsedSeconds)}
          </span>
        </div>
        <span className="text-slate-300 dark:text-slate-700">/</span>
        <div className="flex items-center gap-1">
          <Clock
            className={`w-3.5 h-3.5 ${
              isJobFailed || (isJobComplete && completedQaState === 'failed')
                ? 'text-rose-500'
                : isJobComplete && completedQaState === 'unverified'
                  ? 'text-amber-500'
                  : isJobComplete
                    ? 'text-emerald-500'
                    : isJobCancelled
                      ? 'text-slate-500 dark:text-slate-400'
                      : 'text-sky-500'
            }`}
          />
          <span
            className={`font-bold tabular-nums ${
              isJobFailed || (isJobComplete && completedQaState === 'failed')
                ? 'text-rose-700 dark:text-rose-300'
                : isJobComplete && completedQaState === 'unverified'
                  ? 'text-amber-800 dark:text-amber-300'
                  : isJobComplete
                    ? 'text-emerald-700 dark:text-emerald-400'
                    : isJobCancelled
                      ? 'text-slate-600 dark:text-slate-300'
                      : 'text-sky-700 dark:text-sky-400'
            }`}
          >
            {isJobComplete
              ? completedQaState === 'failed'
                ? t('stepper.qa_failed')
                : completedQaState === 'unverified'
                  ? t('stepper.qa_unverified')
                  : t('stepper.completed')
              : isJobFailed
                ? t('stepper.failed')
                : isJobCancelled
                  ? t('stepper.cancelled')
                  : eta.remainingSeconds === null
                    ? unavailable
                    : `ETA ${formatSeconds(eta.remainingSeconds)}`}
          </span>
        </div>
      </div>

      {/* Section 3: Stream Status & Job Control */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Transport Indicator (honest HTTP polling vs WebSocket) */}
        <div
          className="flex items-center gap-1 text-[11px]"
          data-transport-mode={isWebSocketLive ? 'websocket' : 'http_polling'}
          title={
            isWebSocketLive
              ? 'Live WebSocket telemetry stream'
              : 'HTTP polling telemetry (2s jobs/health, 10s system)'
          }
        >
          {isWebSocketLive ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-emerald-500" />
              <span className="text-emerald-700 dark:text-emerald-400 font-semibold hidden sm:inline">
                {t('system.ws_live')}
              </span>
            </>
          ) : (
            <>
              <Radio className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
              <span className="text-sky-700 dark:text-sky-400 font-semibold hidden sm:inline">
                {t('system.polling')}
              </span>
            </>
          )}
        </div>

        {/* Job Actions */}
        {activeJob && (
          <div className="flex items-center gap-1.5 ml-2">
            {activeJob.status === 'running' ? (
              <button
                onClick={() => controlJob('pause')}
                className="flex items-center gap-1.5 h-7 px-2.5 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30 text-xs font-semibold transition cursor-pointer"
                title={t('common.pause')}
              >
                <Pause className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t('common.pause')}</span>
              </button>
            ) : activeJob.status === 'paused' ? (
              <button
                onClick={() => controlJob('run')}
                className="flex items-center gap-1.5 h-7 px-2.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 text-xs font-semibold transition cursor-pointer"
                title={t('common.resume')}
              >
                <Play className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t('common.resume')}</span>
              </button>
            ) : activeJob.status === 'completed' ? (
              <div
                data-job-status="completed"
                data-qa-state={completedQaState ?? 'unverified'}
                className={`flex items-center gap-1 font-bold text-xs px-2.5 h-7 rounded ${
                  completedQaState === 'failed'
                    ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                    : completedQaState === 'unverified'
                      ? 'bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-500/30'
                      : 'text-emerald-700 dark:text-emerald-400'
                }`}
              >
                {completedQaState === 'passed' ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                ) : (
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                )}
                <span>
                  {completedQaState === 'failed'
                    ? t('system.completed_qa_failed')
                    : completedQaState === 'unverified'
                      ? t('system.completed_qa_unverified')
                      : t('system.completed_qa_passed')}
                </span>
              </div>
            ) : activeJob.status === 'failed' ? (
              <div
                data-job-status="failed"
                className="flex items-center gap-1 bg-rose-500/10 text-rose-700 dark:text-rose-300 border border-rose-500/30 font-bold text-xs px-2.5 h-7 rounded"
              >
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{t('system.status_failed')}</span>
              </div>
            ) : activeJob.status === 'cancelled' ? (
              <div
                data-job-status="cancelled"
                className="flex items-center gap-1 bg-slate-500/10 text-slate-700 dark:text-slate-300 border border-slate-500/30 font-bold text-xs px-2.5 h-7 rounded"
              >
                <Square className="w-3.5 h-3.5 shrink-0" />
                <span>{t('system.status_cancelled')}</span>
              </div>
            ) : (
              <div
                data-job-status={activeJob.status}
                className="flex items-center gap-1 text-slate-700 dark:text-slate-300 font-bold text-xs px-2.5 h-7"
              >
                <Clock className="w-4 h-4 shrink-0" />
                <span>
                  {activeJob.status === 'queued'
                    ? t('system.status_queued')
                    : String(activeJob.status).toUpperCase()}
                </span>
              </div>
            )}

            {(activeJob.status === 'running' || activeJob.status === 'paused') && (
              <button
                onClick={() => controlJob('cancel')}
                className="flex items-center gap-1.5 h-7 px-2.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-700 dark:text-rose-400 border border-rose-500/30 text-xs font-semibold transition cursor-pointer"
                title={t('common.abort')}
              >
                <Square className="w-3 h-3" />
                <span className="hidden sm:inline">{t('common.abort')}</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Stage Telemetry Modal */}
      <StageDetailModal
        stage={selectedStage}
        job={activeJob}
        onClose={() => setSelectedStage(null)}
      />
    </div>
  );
};
