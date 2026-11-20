"""Hàng đợi + 2 luồng xử lý: [tổng hợp] -> [phát].

Trong lúc đoạn n đang phát ra loa, luồng tổng hợp đã làm sẵn đoạn n+1,
nên giữa các câu không có khoảng lặng chờ tổng hợp.
"""
import csv
import itertools
import queue
import threading
import time
from pathlib import Path

from .text_utils import normalize, split_segments

LOG_FIELDS = ["time", "job", "seg", "chars", "audio_s", "synth_ms", "queue_ms", "start_ms", "device_ms"]


class Speaker:
    def __init__(self, engine, sink, emit, max_queue=5, max_chars=400, log_path=None):
        self.engine, self.sink, self.emit = engine, sink, emit
        self.max_chars = max_chars
        self.log_path = Path(log_path) if log_path else None
        self._jobs = queue.Queue(maxsize=max_queue)   # lệnh nói đang chờ
        self._ready = queue.Queue(maxsize=2)          # đoạn đã tổng hợp, chờ phát
        self._gen = 0                                 # tăng mỗi lần Stop để huỷ mọi việc đang dở
        self._active = 0                              # số lệnh nói chưa xong
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._running = True
        sink.prepare(engine.sample_rate)
        for target in (self._synth_loop, self._play_loop):
            threading.Thread(target=target, daemon=True).start()

    # ---- API cho tầng web ----------------------------------------------------
    def status(self):
        with self._lock:
            n = self._active
        return {"type": "status", "state": "speaking" if n else "idle", "pending": n}

    def submit(self, text):
        """Trả (True, job_id) hoặc (False, 'empty' | 'queue_full')."""
        text = normalize(text, self.max_chars)
        if not text:
            return False, "empty"
        with self._lock:
            job = {"id": next(self._ids), "text": text, "gen": self._gen, "t_submit": time.perf_counter()}
            try:
                self._jobs.put_nowait(job)
            except queue.Full:
                return False, "queue_full"
            self._active += 1
        self.emit(self.status())
        return True, job["id"]

    def stop(self):
        """Ngắt ngay: huỷ lệnh đang chờ, đoạn đã tổng hợp và đoạn đang phát."""
        with self._lock:
            self._gen += 1
            self._active = 0
            for q in (self._jobs, self._ready):
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
        self.emit({"type": "caption_clear"})
        self.emit(self.status())

    def close(self):
        self._running = False
        self.sink.close()

    # ---- luồng 1: tổng hợp ---------------------------------------------------
    def _synth_loop(self):
        while self._running:
            try:
                job = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            gen = job["gen"]
            if gen != self._gen:
                continue
            segments = split_segments(job["text"])
            if not segments:
                self._finish_job(gen)
                continue
            for idx, text in enumerate(segments):
                if gen != self._gen:
                    break
                t_start = time.perf_counter()
                audio, error = None, None
                try:
                    audio = self.engine.synthesize(text)
                except Exception as exc:                      # không để một lỗi làm chết luồng
                    error = exc
                item = {"gen": gen, "job": job["id"], "seg": idx, "text": text, "audio": audio,
                        "last": error is not None or idx == len(segments) - 1,
                        "t_submit": job["t_submit"], "t_synth_start": t_start,
                        "t_synth_done": time.perf_counter()}
                if error is not None:
                    self.emit({"type": "error", "message": f"Lỗi tổng hợp giọng nói: {error}"})
                if not self._put(item, gen) or error is not None:
                    break

    def _put(self, item, gen):
        while gen == self._gen and self._running:
            try:
                self._ready.put(item, timeout=0.1)
                return True
            except queue.Full:
                pass
        return False

    # ---- luồng 2: phát + gửi phụ đề -------------------------------------------
    def _play_loop(self):
        while self._running:
            try:
                item = self._ready.get(timeout=0.2)
            except queue.Empty:
                continue
            gen = item["gen"]
            if gen != self._gen:
                continue
            audio, rate = item["audio"], self.engine.sample_rate
            if audio is not None and len(audio):
                self.emit({"type": "caption", "text": item["text"], "job": item["job"],
                           "seg": item["seg"], "duration": round(len(audio) / rate, 2)})
                t_play = time.perf_counter()
                try:
                    self.sink.play(audio, rate, lambda: gen != self._gen)
                except Exception as exc:
                    self.emit({"type": "error", "message": f"Lỗi phát âm thanh: {exc}"})
                self._log(item, len(audio) / rate, t_play)
            if item["last"]:
                self._finish_job(gen)

    def _finish_job(self, gen):
        with self._lock:
            if gen != self._gen:
                return
            self._active = max(0, self._active - 1)
        self.emit(self.status())

    def _log(self, item, audio_s, t_play):
        """start_ms của seg 0 = độ trễ phần mềm từ lúc nhận lệnh đến lúc bắt đầu phát;
        nghe thấy thật ≈ start_ms + device_ms (độ trễ bộ đệm thiết bị)."""
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(LOG_FIELDS)
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), item["job"], item["seg"], len(item["text"]),
                        round(audio_s, 2),
                        round((item["t_synth_done"] - item["t_synth_start"]) * 1000),
                        round((item["t_synth_start"] - item["t_submit"]) * 1000),
                        round((t_play - item["t_submit"]) * 1000),
                        self.sink.latency_ms()])
