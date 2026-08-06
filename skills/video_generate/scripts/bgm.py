"""
背景音乐合成 - NumPy 生成 C大调和弦序列
"""
import os
import numpy as np


SAMPLE_RATE = 44100

# C大调和弦进行
CHORD_PROGRESSION = [
    (261.63, 329.63, 392.00, 523.25),   # C
    (293.66, 369.99, 440.00, 587.33),   # Dm
    (329.63, 392.00, 493.88, 659.25),   # Em
    (349.23, 440.00, 523.25, 698.46),   # F
    (392.00, 493.88, 587.33, 783.99),   # G
    (349.23, 440.00, 523.25, 698.46),   # F
    (261.63, 329.63, 392.00, 523.25),   # C
    (293.66, 369.99, 440.00, 587.33),   # Dm
]


def generate(duration_sec: float, output_path: str,
             chords: list = None, volume: float = 0.15) -> str:
    if chords is None:
        chords = CHORD_PROGRESSION

    total_samples = int(SAMPLE_RATE * duration_sec)
    audio = np.zeros(total_samples, dtype=np.float32)
    chord_dur = 2.0
    fade_len = int(SAMPLE_RATE * 0.3)

    for chord_idx, chord in enumerate(chords):
        start_sample = int(chord_idx * chord_dur * SAMPLE_RATE)
        end_sample = int((chord_idx + 1) * chord_dur * SAMPLE_RATE)
        if start_sample >= total_samples:
            break

        chunk_len = min(end_sample - start_sample, total_samples - start_sample)
        noise = np.zeros(chunk_len, dtype=np.float32)
        t_chunk = np.arange(chunk_len) / SAMPLE_RATE

        for freq in chord:
            amplitude = volume / len(chord)
            sine = np.sin(2 * np.pi * freq * t_chunk) * amplitude
            sine += np.sin(2 * np.pi * freq * 0.5 * t_chunk) * amplitude * 0.3
            noise += sine

        fade = np.ones(chunk_len)
        if chunk_len > fade_len * 2:
            fade[:fade_len] = np.linspace(0, 1, fade_len)
            fade[-fade_len:] = np.linspace(1, 0, fade_len)
        noise *= fade

        if end_sample <= total_samples:
            audio[start_sample:end_sample] += noise
        else:
            audio[start_sample:] += noise[:total_samples - start_sample]

    # 整体淡入淡出
    fade_total = int(SAMPLE_RATE * 1.0)
    audio[:fade_total] *= np.linspace(0, 1, fade_total)
    if total_samples > fade_total:
        audio[-fade_total:] *= np.linspace(1, 0, fade_total)

    import wave
    audio_int16 = (audio * 32767 / np.max(np.abs(audio))).astype(np.int16)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())

    return output_path
