"""
01_test_piper.py - Chạy thử Piper: đo độ trễ, hệ số real-time (RTF) và phát âm thanh.

Cài đặt:
    pip install piper-tts sounddevice
    pip install "piper-tts[alignment]"      # chỉ cần nếu dùng --alignments

Ví dụ:
    python 01_test_piper.py --list-devices
    python 01_test_piper.py --model voices/en_US-lessac-medium.onnx
    python 01_test_piper.py --model voices/en_US-lessac-medium.onnx --device "CABLE Input"
    python 01_test_piper.py --model voices/en_US-lessac-medium.onnx --alignments
"""
import argparse
import time

import numpy as np
from piper import PiperVoice

DEFAULT_TEXT = (
    "Hello everyone, welcome to my stream. "
    "Thanks for the follow, I really appreciate it."
)


def list_devices():
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            host = sd.query_hostapis(d["hostapi"])["name"]
            print(f"[{i:>2}] {d['name']}  ({host})")


def find_output_device(query):
    """Nhận số thứ tự hoặc một đoạn tên thiết bị, ví dụ 'CABLE Input'."""
    import sounddevice as sd

    if query.isdigit():
        return int(query)
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and query.lower() in d["name"].lower():
            return i
    raise SystemExit(f"Không tìm thấy thiết bị phát chứa '{query}'. Chạy --list-devices.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="đường dẫn file .onnx (file .onnx.json nằm cạnh nó)")
    ap.add_argument("--text", default=DEFAULT_TEXT)
    ap.add_argument("--device", help="số thứ tự hoặc tên thiết bị phát; bỏ trống = chỉ đo, không phát")
    ap.add_argument("--alignments", action="store_true", help="thử lấy mốc thời gian từng âm vị")
    ap.add_argument("--list-devices", action="store_true")
    args = ap.parse_args()

    if args.list_devices:
        return list_devices()
    if not args.model:
        ap.error("cần --model")

    t0 = time.perf_counter()
    voice = PiperVoice.load(args.model, include_alignments=args.alignments)
    sr = voice.config.sample_rate
    print(f"Nạp model: {time.perf_counter() - t0:.2f}s | sample_rate = {sr} Hz")

    # Lần chạy đầu thường chậm hơn (khởi tạo ONNX Runtime) nên chạy khởi động trước.
    list(voice.synthesize("Warm up."))

    print(f"\nVăn bản: {args.text}\n")
    chunks = []
    first_chunk_after = None
    t_start = t_prev = time.perf_counter()

    # synthesize() là generator: mỗi câu chỉ được tổng hợp khi vòng lặp lấy tới nó.
    for i, chunk in enumerate(
        voice.synthesize(args.text, include_alignments=args.alignments), start=1
    ):
        now = time.perf_counter()
        dur = len(chunk.audio_float_array) / chunk.sample_rate
        if first_chunk_after is None:
            first_chunk_after = now - t_start
        print(
            f"câu {i}: audio {dur:.2f}s | tổng hợp mất {now - t_prev:.3f}s "
            f"| RTF = {(now - t_prev) / dur:.2f}"
        )

        if args.alignments:
            if chunk.phoneme_alignments:
                t = 0.0
                for a in chunk.phoneme_alignments[:6]:
                    print(f"    âm vị {a.phoneme!r:>5} bắt đầu ở {t:.3f}s")
                    t += a.num_samples / chunk.sample_rate
            else:
                print("    (model/phiên bản này chưa trả về mốc thời gian âm vị)")

        chunks.append(chunk.audio_float_array)
        t_prev = time.perf_counter()

    total = time.perf_counter() - t_start
    audio = np.concatenate(chunks)
    audio_sec = len(audio) / sr
    print(f"\nĐến khi có âm thanh đầu tiên: {first_chunk_after:.3f}s")
    print(f"Tổng: tổng hợp {total:.3f}s cho {audio_sec:.2f}s audio (RTF = {total / audio_sec:.2f})")
    print("RTF < 1 nghĩa là nhanh hơn thời gian thực.")

    if args.device:
        import sounddevice as sd

        device = find_output_device(args.device)
        # Ghép thành stereo vì nhiều thiết bị (kể cả VB-Cable) mở kênh ổn định hơn với 2 kênh.
        stereo = np.column_stack([audio, audio])
        print(f"\nĐang phát ra thiết bị [{device}] {sd.query_devices(device)['name']} ...")
        sd.play(stereo, samplerate=sr, device=device)
        sd.wait()


if __name__ == "__main__":
    main()
