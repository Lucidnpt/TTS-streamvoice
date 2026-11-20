"""Phát audio ra thiết bị (vd. VB-CABLE) bằng luồng blocking, có thể ngắt giữa chừng."""
import time

import numpy as np

# Thứ tự thử các host API của Windows (nhỏ hơn = thử trước). MME chịu mọi sample rate nhất.
HOST_RANK = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}


def candidate_devices(query):
    """Danh sách chỉ số thiết bị phát khớp với `query`, MME đứng đầu.
    None/'' = loa mặc định; một con số = đúng thiết bị đó."""
    import sounddevice as sd

    if query is None or query == "":
        return [None]
    if isinstance(query, int) or str(query).isdigit():
        return [int(query)]
    hosts = sd.query_hostapis()
    found = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and str(query).lower() in d["name"].lower():
            found.append((HOST_RANK.get(hosts[d["hostapi"]]["name"], 9), i))
    if not found:
        raise ValueError(f"Không tìm thấy thiết bị phát chứa '{query}'. "
                         "Chạy: python -m backend.audio_out  để xem danh sách.")
    return [i for _, i in sorted(found)]


class SoundDeviceSink:
    def __init__(self, device=None, latency="low", block_ms=30):
        import sounddevice as sd

        self.sd = sd
        self.candidates = candidate_devices(device)
        self.latency = latency
        self.block_ms = block_ms
        self._stream = None
        self._rate = None

    def prepare(self, sample_rate):
        """Mở luồng sẵn từ lúc khởi động. Thử lần lượt từng thiết bị khớp tên, mỗi thiết bị thử
        latency đã cấu hình rồi 'high'; dùng cái đầu tiên mở được."""
        if self._stream is not None and self._rate == sample_rate:
            return
        self.close()
        last_error = None
        for device in self.candidates:
            for latency in dict.fromkeys([self.latency, "high"]):
                stream = None
                try:
                    stream = self.sd.OutputStream(samplerate=sample_rate, device=device, channels=2,
                                                  dtype="float32", latency=latency)
                    stream.start()
                except self.sd.PortAudioError as exc:
                    last_error = exc
                    if stream is not None:
                        stream.close()
                    continue
                self._stream, self._rate = stream, sample_rate
                self._describe(device, latency)
                return
        raise RuntimeError(
            f"Không mở được thiết bị phát nào ({last_error}). Chạy 'python -m backend.audio_out', "
            "đặt output_device trong config.json thành số thứ tự của một dòng (MME), "
            "và tắt 'Allow applications to take exclusive control' của thiết bị trong Sound settings.")

    def _describe(self, device, latency):
        try:
            info = self.sd.query_devices(device, "output")
            host = self.sd.query_hostapis(info["hostapi"])["name"]
            print(f"Phát ra: {info['name']} ({host}), latency={latency}")
        except Exception:
            pass

    def play(self, audio, sample_rate, should_stop):
        """Phát hết thì trả True; bị ngắt (should_stop() = True) thì trả False."""
        self.prepare(sample_rate)
        stereo = np.column_stack([audio, audio]).astype(np.float32)   # nhân đôi thành 2 kênh
        block = max(1, int(sample_rate * self.block_ms / 1000))
        for i in range(0, len(stereo), block):
            if should_stop():
                return False
            self._stream.write(stereo[i:i + block])
        return True

    def latency_ms(self):
        return round(self._stream.latency * 1000) if self._stream else 0

    def close(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None


class NullSink:
    """Không phát ra loa, chỉ chờ đúng thời lượng audio (dùng cho --dry-run)."""

    def prepare(self, sample_rate):
        pass

    def play(self, audio, sample_rate, should_stop):
        end = time.perf_counter() + len(audio) / sample_rate
        while time.perf_counter() < end:
            if should_stop():
                return False
            time.sleep(0.01)
        return True

    def latency_ms(self):
        return 0

    def close(self):
        pass


if __name__ == "__main__":
    # python -m backend.audio_out            -> liệt kê thiết bị phát
    # python -m backend.audio_out "CABLE"    -> phát thử tiếng bíp 1 giây ra thiết bị đó
    import sys

    import sounddevice as sd

    if len(sys.argv) < 2:
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                print(f"[{i:>2}] {d['name']}  ({sd.query_hostapis(d['hostapi'])['name']})")
    else:
        sr = 22050
        t = np.arange(sr) / sr
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        sink = SoundDeviceSink(sys.argv[1])
        sink.prepare(sr)
        sink.play(tone, sr, lambda: False)
        time.sleep(0.3)
        sink.close()