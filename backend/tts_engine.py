"""Lớp bọc Piper. FakeEngine dùng cho --dry-run (không cần model)."""
import time

import numpy as np


class PiperEngine:
    """Nạp model một lần, tổng hợp một đoạn văn bản thành mảng float32 mono."""

    def __init__(self, model_path, speed=1.0):
        from piper import PiperVoice, SynthesisConfig

        t0 = time.perf_counter()
        self.voice = PiperVoice.load(model_path)
        self.sample_rate = self.voice.config.sample_rate
        length_scale = None
        if speed != 1.0:
            length_scale = self.voice.config.length_scale / speed
        self.syn_config = SynthesisConfig(length_scale=length_scale)
        list(self.voice.synthesize("Warm up.", self.syn_config))   # khởi động ONNX Runtime
        self.load_seconds = time.perf_counter() - t0

    def synthesize(self, text):
        chunks = [c.audio_float_array for c in self.voice.synthesize(text, self.syn_config)]
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


class FakeEngine:
    """Sinh im lặng, độ dài tỉ lệ số ký tự (~60 ms/ký tự) để thử toàn bộ luồng."""

    sample_rate = 22050

    def synthesize(self, text):
        time.sleep(0.05)
        return np.zeros(int(self.sample_rate * 0.06 * len(text)), dtype=np.float32)


if __name__ == "__main__":    
    import sys

    engine = PiperEngine(sys.argv[1])
    text = sys.argv[2] if len(sys.argv) > 2 else "Hello everyone, welcome to my stream."
    t0 = time.perf_counter()
    audio = engine.synthesize(text)
    took = time.perf_counter() - t0
    secs = len(audio) / engine.sample_rate
    print(f"nạp model {engine.load_seconds:.2f}s | {secs:.2f}s audio trong {took:.3f}s (RTF {took / secs:.2f})")
