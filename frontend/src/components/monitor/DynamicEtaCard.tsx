import React, { useState, useEffect } from 'react';
import { useJob } from '@/context/JobContext';
import { useTranslation } from '@/context/I18nContext';
import { formatSeconds, formatRtf, resolveActiveStageIndex, PIPELINE_STAGES } from '@/lib/utils';
import { deriveEtaTelemetry, finiteNumber, resolveCompletedQaState } from '@/lib/telemetry';
import { AlertTriangle, Clock, Zap, Timer, CheckCircle, Activity } from 'lucide-react';

export const DynamicEtaCard: React.FC = () => {
  const { activeJob } = useJob();
  const { language, t } = useTranslation();

  const [liveElapsed, setLiveElapsed] = useState<number | null>(null);

  const isCompleted = activeJob?.status === 'completed';
  const isFailed = activeJob?.status === 'failed';
  const isCancelled = activeJob?.status === 'cancelled';
  const isRunning = activeJob?.status === 'running';
  const completedQaState = resolveCompletedQaState(activeJob);
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
  const completionTimeStr = eta.completionAtMs === null ? null : new Date(eta.completionAtMs).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const activeStageIdx = activeJob && activeJob.stage
    ? resolveActiveStageIndex(activeJob.stage, eta.progress ?? 0)
    : -1;
  const currentStageDef = activeStageIdx >= 0 ? PIPELINE_STAGES[activeStageIdx] : null;
  const unavailable = t('common.unavailable');

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg p-4 shadow-sm font-mono">
      <div className="flex items-center justify-between mb-3 border-b border-slate-100 dark:border-slate-800/80 pb-2">
        <div className="flex items-center gap-2">
          <Activity
            className={`w-4 h-4 ${
              isRunning
                ? 'text-orange-500 animate-pulse'
                : isFailed || (isCompleted && completedQaState === 'failed')
                  ? 'text-rose-500'
                  : isCompleted && completedQaState === 'unverified'
                    ? 'text-amber-500'
                    : isCompleted
                      ? 'text-emerald-500'
                      : 'text-slate-400'
            }`}
          />
          <h3 className="text-xs font-bold tracking-wider text-slate-800 dark:text-slate-200 uppercase">
            {t('eta.title')}
          </h3>
        </div>
        <span
          data-qa-state={completedQaState ?? undefined}
          className={`text-2xs font-semibold px-2 py-0.5 rounded-full ${
            isCompleted
              ? completedQaState === 'failed'
                ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                : completedQaState === 'unverified'
                  ? 'bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-500/30'
                  : 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
              : isFailed
                ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                : isCancelled
                  ? 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border border-slate-500/30'
                  : eta.remainingSeconds === null
                    ? 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border border-slate-500/20'
                    : 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border border-cyan-500/20'
          }`}
        >
          {isCompleted
            ? completedQaState === 'failed'
              ? 'PIPELINE_COMPLETE · QA_FAILED'
              : completedQaState === 'unverified'
                ? 'PIPELINE_COMPLETE · QA_UNVERIFIED'
                : 'PIPELINE_COMPLETE · QA_PASSED'
            : isFailed
              ? 'PIPELINE_FAILED'
              : isCancelled
                ? 'PIPELINE_CANCELLED'
                : eta.remainingSeconds === null
                  ? unavailable
                  : 'REALTIME_ESTIMATE'}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1 mb-4">
        <div className="flex justify-between text-2xs text-slate-500">
          <span>{currentStageDef ? (language === 'vi' ? currentStageDef.labelVi : currentStageDef.labelEn) : unavailable}</span>
          <span className="font-bold text-slate-700 dark:text-slate-300">
            {eta.progress === null ? unavailable : `${Math.round(eta.progress * 100)}%`}
          </span>
        </div>
        <div className="w-full h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              isCompleted
                ? completedQaState === 'failed'
                  ? 'bg-rose-500'
                  : completedQaState === 'unverified'
                    ? 'bg-amber-500'
                    : 'bg-emerald-500'
                : isFailed
                  ? 'bg-rose-500'
                  : isCancelled
                    ? 'bg-slate-400 dark:bg-slate-600'
                    : isRunning
                      ? 'bg-gradient-to-r from-orange-500 to-amber-500 animate-pulse'
                      : 'bg-amber-500'
            }`}
            style={{ width: eta.progress === null ? '0%' : `${Math.round(eta.progress * 100)}%` }}
          />
        </div>
      </div>

      {/* 4-Column Metric Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        {/* Elapsed */}
        <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded border border-slate-100 dark:border-slate-800">
          <div className="text-2xs text-slate-400 flex items-center gap-1 mb-1">
            <Timer className="w-3 h-3 text-slate-400" />
            <span>{t('eta.elapsed')}</span>
          </div>
          <div className="text-sm font-bold text-slate-800 dark:text-slate-200 tabular-nums">
            {eta.elapsedSeconds === null ? unavailable : formatSeconds(eta.elapsedSeconds)}
          </div>
        </div>

        {/* Remaining */}
        <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded border border-slate-100 dark:border-slate-800">
          <div className="text-2xs text-slate-400 flex items-center gap-1 mb-1">
            <Clock className="w-3 h-3 text-sky-400" />
            <span>{t('eta.remaining')}</span>
          </div>
          <div className="text-sm font-bold text-sky-600 dark:text-sky-400 tabular-nums">
            {eta.remainingSeconds === null ? unavailable : formatSeconds(eta.remainingSeconds)}
          </div>
        </div>

        {/* RTF Speed */}
        <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded border border-slate-100 dark:border-slate-800">
          <div className="text-2xs text-slate-400 flex items-center gap-1 mb-1">
            <Zap className="w-3 h-3 text-amber-400" />
            <span>{t('eta.speed')}</span>
          </div>
          <div className="text-sm font-bold text-amber-600 dark:text-amber-400">
            {eta.realTimeFactor === null ? unavailable : formatRtf(eta.realTimeFactor)}
          </div>
        </div>

        {/* Est. Completion Clock */}
        <div className="bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded border border-slate-100 dark:border-slate-800">
          <div className="text-2xs text-slate-400 flex items-center gap-1 mb-1">
            {isFailed || (isCompleted && completedQaState === 'failed') ? (
              <AlertTriangle className="w-3 h-3 text-rose-500" />
            ) : isCompleted && completedQaState === 'unverified' ? (
              <AlertTriangle className="w-3 h-3 text-amber-500" />
            ) : isCancelled ? (
              <Clock className="w-3 h-3 text-slate-400" />
            ) : (
              <CheckCircle className="w-3 h-3 text-emerald-400" />
            )}
            <span>{t('eta.completion')}</span>
          </div>
          <div
            className={`text-sm font-bold tabular-nums ${
              isFailed || (isCompleted && completedQaState === 'failed')
                ? 'text-rose-700 dark:text-rose-300'
                : isCompleted && completedQaState === 'unverified'
                  ? 'text-amber-800 dark:text-amber-300'
                  : isCancelled
                    ? 'text-slate-600 dark:text-slate-300'
                    : 'text-emerald-600 dark:text-emerald-400'
            }`}
          >
            {isCompleted
              ? completedQaState === 'failed'
                ? t('stepper.qa_failed')
                : completedQaState === 'unverified'
                  ? t('stepper.qa_unverified')
                  : 'DONE'
              : isFailed
                ? t('stepper.failed')
                : isCancelled
                  ? t('stepper.cancelled')
                  : completionTimeStr ?? unavailable}
          </div>
        </div>
      </div>
    </div>
  );
};
