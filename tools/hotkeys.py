"""Phím tắt toàn cục: bấm tổ hợp phím (kể cả khi đang chơi game) để nói câu nhanh hoặc dừng.

Chạy song song với run.py:   python tools/hotkeys.py
Phím tắt đọc từ "phrases" và "stop_hotkey" trong config.json.
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def post(base, pin, path, payload=None):
    req = urllib.request.Request(base + path, data=json.dumps(payload or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Pin": pin})
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except Exception as exc:
        print("Lỗi gọi StreamVoice:", exc)


def main():
    import keyboard

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    host = "127.0.0.1" if cfg.get("host", "") in ("0.0.0.0", "") else cfg["host"]
    base, pin = f"http://{host}:{cfg.get('port', 8765)}", str(cfg.get("pin", "1234"))

    for phrase in cfg.get("phrases", []):
        if phrase.get("hotkey"):
            keyboard.add_hotkey(phrase["hotkey"], post, args=(base, pin, "/api/speak", {"text": phrase["text"]}))
            print(f"{phrase['hotkey']:>16}  nói: {phrase['text']}")
    if cfg.get("stop_hotkey"):
        keyboard.add_hotkey(cfg["stop_hotkey"], post, args=(base, pin, "/api/stop"))
        print(f"{cfg['stop_hotkey']:>16}  dừng")
    print("Đang lắng nghe phím tắt. Nhấn Ctrl+C để thoát.")
    keyboard.wait()


if __name__ == "__main__":
    main()
