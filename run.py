"""Khởi chạy StreamVoice.

    python run.py --dry-run     # thử giao diện/WebSocket/hàng đợi, chưa cần Piper và loa
    python run.py               # chạy thật: Piper -> thiết bị phát trong config.json
"""
import argparse

import uvicorn

from backend.app import create_app
from backend.config import load_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="không dùng Piper/loa")
    ap.add_argument("--config", help="đường dẫn config.json khác")
    args = ap.parse_args()

    cfg = load_config(args.config)
    shown = "127.0.0.1" if cfg["host"] in ("0.0.0.0", "") else cfg["host"]
    base = f"http://{shown}:{cfg['port']}"
    print(f"Control panel : {base}/control")
    print(f"Overlay (OBS) : {base}/overlay")
    if cfg["host"] not in ("127.0.0.1", "localhost") and cfg["pin"] == "1234":
        print("CẢNH BÁO: đang mở ra mạng LAN nhưng PIN vẫn là 1234, hãy đổi trong config.json.")
    uvicorn.run(create_app(args.dry_run, cfg), host=cfg["host"], port=cfg["port"], log_level="warning")


if __name__ == "__main__":
    main()
