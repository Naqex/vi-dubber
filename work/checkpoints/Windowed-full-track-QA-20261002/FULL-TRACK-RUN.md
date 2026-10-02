# Full-track local diagnostic — prepared launch packet

Scope: retained Job12 voice only; no provider, translation, TTS, audio repair, model download, policy change or canonical QA/state publication. Candidate local re-ASR uses cached large-v3 CUDA FP16 batch4, Vietnamese, 143 source windows of300s with2s context, maximum304s input. Output is a new separate diagnostic folder. A complete diagnostic does not clear122 failed segments or replace human listening/product promotion.

## Before launch

Review the frozen source commit/checkpoint. Recheck no retained Job12 run.lock/active producer and current RAM/GPU/disk. `--plan-only` reads hashes/headers and cached metadata only; verify `full-plan-v2.json` fingerprint before running. Source/model/code/version drift must be reconciled, not worked around by deleting cache/checkpoints.

```powershell
cd D:/ANNAM/TradingWorkspace/projects/vi-dubber
& ./.venv/Scripts/python.exe scripts/check_full_track_qa.py --job-dir work/job-8dc51f8a892aba21 --plan-only --window-seconds 300 --context-seconds 2
```

## First launch — root review required

Do not execute if the named output already exists without reconciling its checkpoint/lease/PID. Use hidden detached `Start-Process` with exact arguments, stdout/stderr and save returned PID+command+start time in this owning checkpoint. Do not wait synchronously for all143 windows or start a duplicate after a tool timeout.

```powershell
$taskRoot = 'D:/ANNAM/TradingWorkspace/projects/vi-dubber'
$taskEvidence = Join-Path $taskRoot 'work/checkpoints/Windowed-full-track-QA-20261002'
$taskArgs = @('scripts/check_full_track_qa.py','--job-dir','work/job-8dc51f8a892aba21','--output','work/artifacts/full-track-qa-job12-20261002','--window-seconds','300','--context-seconds','2','--all-windows')
$taskWorker = Start-Process -FilePath (Join-Path $taskRoot '.venv/Scripts/python.exe') -ArgumentList $taskArgs -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskEvidence 'full-stdout.txt') -RedirectStandardError (Join-Path $taskEvidence 'full-stderr.txt') -PassThru
[pscustomobject]@{pid=$taskWorker.Id;started_at=[DateTimeOffset]::Now.ToString('o');arguments=$taskArgs;output='work/artifacts/full-track-qa-job12-20261002'} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $taskEvidence 'full-launch.json')
```

Effects: fingerprints source/model/code pre/post; creates only this new diagnostic output, exclusive `run.lock`, small per-window transcript checkpoint/diagnostic and one temporary WAV at a time. Own WAV removed after every success/failure; own lease removed on ordinary exit. No retained file changes. Existing lease helper may reclaim only a dead owned diagnostic-folder lease after PID checking; retained-job lease is never reclaimed by this tool. Network/DNS denied in the CLI.

## Observe and resume

Read `full-launch.json`, its process tree and `work/artifacts/full-track-qa-job12-20261002/checkpoint.json`. Checkpoint's Python worker PID may differ from the Windows `.venv` launcher PID; track both. `completed` is atomically published after each verified window. Confirm source/config/code/model fingerprint and retained inputs remain the same. Read logs only on progress changes/failure.

On normal incomplete/failure exit, preserve checkpoint/logs. After confirming old worker is gone and ownership is reconciled, launch the exact same arguments to the exact same output with newly named attempt log/PID receipt. Validated windows are skipped; `failed_resume_available` does not mean completed. Never use `--fresh`, delete retained cache/locks/receipts or infer success from elapsed time.

Only when `diagnostic.json.status=complete_diagnostic`, all143 windows cover42,831.561s and source identity recheck succeeds, review transcript boundary behavior, retained flags, resource evidence and human listening separately. Any later code/model/config change invalidates resume; root must decide whether to keep the old attempt as evidence and start a new explicit diagnostic. No automatic canonical acceptance update is performed.
