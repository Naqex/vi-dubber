from __future__ import annotations

import math
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vi_dubber.audio import (
    WAVEFORM_BLOCK_FRAMES,
    WAVEFORM_PROBE_FRAMES,
    WAVEFORM_PROBES_PER_BAR,
    _extract_waveform_peaks_from_stream,
    evaluate_reference_clarity,
    extract_bounded_waveform_peaks,
    normalize_loudness,
    resolve_loudness_profile,
)
from vi_dubber.media import measure_mix_metrics


def _create_wav(
    path: Path,
    *,
    duration: float = 3.0,
    sample_rate: int = 48000,
    freq: float = 440.0,
    amplitude: float = 0.5,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, duration, int(round(sample_rate * duration)), endpoint=False, dtype=np.float32)
    # Generate modulated tone to simulate speech dynamics with pause
    modulator = 0.5 * (1.0 + np.sin(2.0 * np.pi * 3.0 * t))
    audio = amplitude * np.sin(2.0 * np.pi * freq * t) * modulator
    # Add quiet tail to ensure noise floor
    audio[-int(sample_rate * 0.5) :] = 1e-4 * np.random.randn(int(sample_rate * 0.5))
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")
    return path


def test_evaluate_reference_clarity_on_synthetic_signal(tmp_path: Path) -> None:
    wav_path = _create_wav(tmp_path / "ref.wav", duration=4.0, freq=300.0, amplitude=0.4)
    result = evaluate_reference_clarity(wav_path)

    assert "energy_variance" in result
    assert "zero_crossing_rate" in result
    assert "estimated_snr" in result
    assert "snr_db" in result
    assert "clarity_score" in result
    assert "speech_ratio" in result
    assert "clipping_ratio" in result

    assert math.isfinite(result["energy_variance"])
    assert result["energy_variance"] > 0.0
    assert 0.0 <= result["zero_crossing_rate"] <= 1.0
    assert result["estimated_snr"] > 0.0
    assert 0.0 <= result["clarity_score"] <= 1.0
    assert result["clipping_ratio"] == 0.0


def test_evaluate_reference_clarity_on_silent_signal(tmp_path: Path) -> None:
    silent_wav = tmp_path / "silence.wav"
    sf.write(str(silent_wav), np.zeros(24000, dtype=np.float32), 48000, subtype="PCM_16")
    result = evaluate_reference_clarity(silent_wav)

    assert result["energy_variance"] == 0.0
    assert result["zero_crossing_rate"] == 0.0
    assert result["estimated_snr"] == 0.0
    assert result["clarity_score"] == 0.0


def test_resolve_loudness_profile() -> None:
    # YouTube profile defaults to -14.0 LUFS, -1.5 dBTP
    yt_lufs, yt_tp = resolve_loudness_profile("youtube")
    assert yt_lufs == -14.0
    assert yt_tp == -1.5

    # Broadcast profile defaults to -23.0 LUFS, -1.0 dBTP
    bc_lufs, bc_tp = resolve_loudness_profile("broadcast")
    assert bc_lufs == -23.0
    assert bc_tp == -1.0

    # Custom overrides take priority
    custom_lufs, custom_tp = resolve_loudness_profile("youtube", custom_lufs=-16.0, custom_true_peak=-2.0)
    assert custom_lufs == -16.0
    assert custom_tp == -2.0


def test_normalize_loudness_produces_valid_audio(tmp_path: Path) -> None:
    src_wav = _create_wav(tmp_path / "input.wav", duration=2.5, amplitude=0.8)
    dst_wav = tmp_path / "normalized.wav"

    out_path = normalize_loudness(src_wav, dst_wav, profile="youtube", target_lufs=-14.0, target_true_peak_db=-1.5)
    assert out_path.is_file()
    assert out_path.stat().st_size > 0

    metrics = measure_mix_metrics(out_path, target_lufs=-14.0, target_true_peak_db=-1.5)
    assert math.isfinite(metrics["integrated_lufs"])
    assert math.isfinite(metrics["true_peak_db"])


def test_extract_bounded_waveform_peaks_streaming_full_real_wav(tmp_path: Path) -> None:
    sample_rate = 48_000
    n_half = sample_rate  # 1s quiet + 1s burst = 2s stereo WAV
    quiet = np.zeros((n_half, 2), dtype=np.float32)
    t = np.linspace(0.0, 1.0, n_half, endpoint=False, dtype=np.float32)
    burst_ch0 = 0.6 * np.sin(2.0 * np.pi * 440.0 * t)
    burst_ch1 = 0.2 * np.sin(2.0 * np.pi * 220.0 * t)
    burst = np.stack([burst_ch0, burst_ch1], axis=1)
    audio = np.concatenate([quiet, burst], axis=0)

    wav_path = tmp_path / "stereo_half_burst.wav"
    sf.write(str(wav_path), audio, sample_rate, subtype="PCM_16")

    result = extract_bounded_waveform_peaks(wav_path, bars=64)
    assert result["bars"] == 64
    assert len(result["peaks"]) == 64
    assert result["sampling_mode"] == "streaming_full"
    assert result["channels"] == 2
    assert result["sample_rate"] == sample_rate
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.01)
    assert result["max_read_buffer_frames"] <= WAVEFORM_BLOCK_FRAMES
    assert max(result["peaks"][:32]) == 0.0
    assert min(result["peaks"][32:]) > 0.55


def test_extract_bounded_waveform_peaks_handles_empty_and_tiny_wav(tmp_path: Path) -> None:
    empty_wav = tmp_path / "empty.wav"
    sf.write(str(empty_wav), np.zeros((0, 1), dtype=np.float32), 48_000, subtype="PCM_16")
    empty_res = extract_bounded_waveform_peaks(empty_wav, bars=32)
    assert empty_res["sampling_mode"] == "empty"
    assert empty_res["peaks"] == [0.0] * 32
    assert empty_res["frames_scanned"] == 0

    tiny_wav = tmp_path / "tiny.wav"
    tiny_samples = np.linspace(0.1, 0.8, 12, dtype=np.float32)
    sf.write(str(tiny_wav), tiny_samples, 48_000, subtype="PCM_16")
    tiny_res = extract_bounded_waveform_peaks(tiny_wav, bars=64)
    assert tiny_res["sampling_mode"] == "streaming_full"
    assert len(tiny_res["peaks"]) == 64
    assert tiny_res["peaks"][0] > 0.05
    assert tiny_res["peaks"][-1] > 0.75


def test_extract_bounded_waveform_peaks_windowed_seek_real_wav(tmp_path: Path) -> None:
    sample_rate = 16_000
    total_frames = sample_rate * 4
    audio = np.zeros(total_frames, dtype=np.float32)
    # Place clear tone bursts in the first and final quarters.
    t = np.linspace(0.0, 1.0, sample_rate, endpoint=False, dtype=np.float32)
    audio[:sample_rate] = 0.7 * np.sin(2.0 * np.pi * 440.0 * t)
    audio[-sample_rate:] = 0.5 * np.sin(2.0 * np.pi * 880.0 * t)
    wav_path = tmp_path / "long_seek.wav"
    sf.write(str(wav_path), audio, sample_rate, subtype="PCM_16")

    result = extract_bounded_waveform_peaks(
        wav_path,
        bars=16,
        full_scan_max_frames=16_000,
        probes_per_bar=4,
        probe_frames=256,
    )
    assert result["sampling_mode"] == "windowed_seek"
    assert result["max_read_buffer_frames"] <= 256
    assert result["frames_scanned"] < total_frames
    assert min(result["peaks"][:4]) > 0.6
    assert max(result["peaks"][4:12]) == 0.0
    assert min(result["peaks"][12:]) > 0.4


def test_extract_bounded_waveform_peaks_near_12h_memory_budget() -> None:
    """Prove O(1) memory and bounded I/O for a 12-hour 48kHz stereo track (~8.29 GiB PCM16)."""
    sample_rate = 48_000
    duration_seconds = 12 * 3600  # 43,200 s
    total_frames = sample_rate * duration_seconds  # 2,073,600,000 frames
    channels = 2
    file_bytes = total_frames * channels * 2 + 44  # ~8.29 GiB PCM16 WAV

    # Active bursts spanning buckets 0 (hour 0), 32 (hour 6), and 63 (hour 11.9).
    bucket_len = total_frames // 64
    burst_ranges = (
        (0, bucket_len, 0.8),
        (32 * bucket_len, 33 * bucket_len, 0.6),
        (63 * bucket_len, total_frames, 0.7),
    )

    class _Virtual12hAudioStream:
        def __init__(self) -> None:
            self.pos = 0
            self.max_requested_frames = 0
            self.total_read_frames = 0

        def seekable(self) -> bool:
            return True

        def seek(self, offset: int) -> int:
            self.pos = max(0, min(total_frames, int(offset)))
            return self.pos

        def read(self, frames: int = -1, dtype: str = "float32", always_2d: bool = True) -> np.ndarray:
            assert frames > 0, "bounded waveform extractor must never call unbounded read(-1)"
            n = min(int(frames), total_frames - self.pos)
            self.max_requested_frames = max(self.max_requested_frames, n)
            self.total_read_frames += n
            start = self.pos
            end = start + n
            self.pos = end
            buf = np.zeros((n, channels), dtype=dtype)
            for b_start, b_end, amp in burst_ranges:
                lo = max(start, b_start)
                hi = min(end, b_end)
                if hi > lo:
                    buf[lo - start : hi - start, 0] = amp
            return buf if always_2d else buf[:, 0]

    stream = _Virtual12hAudioStream()
    tracemalloc.start()
    try:
        result = _extract_waveform_peaks_from_stream(
            stream,
            total_frames=total_frames,
            sample_rate=sample_rate,
            channels=channels,
            file_bytes=file_bytes,
            bars=64,
        )
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result["sampling_mode"] == "windowed_seek"
    assert result["duration_seconds"] == pytest.approx(43_200.0)
    assert result["max_read_buffer_frames"] <= WAVEFORM_PROBE_FRAMES
    assert stream.max_requested_frames <= WAVEFORM_PROBE_FRAMES
    assert result["frames_scanned"] <= 64 * WAVEFORM_PROBES_PER_BAR * WAVEFORM_PROBE_FRAMES
    assert peak_bytes < 4 * 1024 * 1024, f"Peak traced memory exceeded 4 MiB: {peak_bytes}"
    assert result["peaks"][0] == pytest.approx(0.8, abs=0.01)
    assert result["peaks"][32] == pytest.approx(0.6, abs=0.01)
    assert result["peaks"][63] == pytest.approx(0.7, abs=0.01)
    assert result["peaks"][10] == 0.0
    assert result["peaks"][50] == 0.0


def test_extract_bounded_waveform_peaks_validation_errors(tmp_path: Path) -> None:
    wav_path = _create_wav(tmp_path / "valid.wav", duration=1.0)
    with pytest.raises(ValueError, match="bars"):
        extract_bounded_waveform_peaks(wav_path, bars=8)
    with pytest.raises(ValueError, match="bars"):
        extract_bounded_waveform_peaks(wav_path, bars=1024)
    with pytest.raises(ValueError, match="bars"):
        extract_bounded_waveform_peaks(wav_path, bars=True)  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        extract_bounded_waveform_peaks(tmp_path / "missing.wav")

    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"not-a-valid-audio-file")
    with pytest.raises(ValueError, match="waveform"):
        extract_bounded_waveform_peaks(corrupt)
