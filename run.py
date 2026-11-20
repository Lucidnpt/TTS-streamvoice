"""Khởi chạy StreamVoice.

    python run.py                   # mở app desktop (cửa sổ riêng) + server cho overlay OBS
    python run.py --dry-run         # như trên nhưng chưa cần Piper và loa (thử giao diện)
    python run.py --web             # chỉ chạy server, điều khiển bằng trình duyệt / điện thoại
"""
import argparse
import sys
import threading
import time
import webbrowser

import uvicorn

from backend.app import create_app
from backend.config import load_config


class DesktopApi:
    """Hàm JavaScript gọi được qua window.pywebview.api trong cửa sổ app."""

    def open_url(self, url):
        if str(url).startswith(("http://127.0.0.1", "http://localhost")):
            webbrowser.open(url)


def run_desktop(server, local_base, pin):
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise SystemExit("Server không khởi động được (xem lỗi phía trên).")
        time.sleep(0.05)

    url = f"{local_base}/control#pin={pin}"
    try:
        import webview
    except ImportError:
        print("Chưa cài pywebview (pip install pywebview), mở bằng trình duyệt thay thế.")
        webbrowser.open(url)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
    else:
        webview.create_window("StreamVoice", url, width=920, height=780, min_size=(640, 520),
                              js_api=DesktopApi(), background_color="#1f2633")
        webview.start()            # chặn tới khi đóng cửa sổ

    server.should_exit = True
    thread.join(timeout=5)


def main():
    # Console Windows / output chuyển hướng ra file có thể không phải UTF-8 -> print tiếng Việt bị lỗi.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="không dùng Piper/loa")
    ap.add_argument("--web", action="store_true", help="chỉ chạy server, không mở cửa sổ app")
    ap.add_argument("--config", help="đường dẫn config.json khác")
    args = ap.parse_args()

    cfg = load_config(args.config)
    shown = "127.0.0.1" if cfg["host"] in ("0.0.0.0", "") else cfg["host"]
    base = f"http://{shown}:{cfg['port']}"
    print(f"Control panel : {base}/control")
    print(f"Overlay (OBS) : {base}/overlay")
    if cfg["host"] not in ("127.0.0.1", "localhost") and cfg["pin"] == "1234":
        print("CẢNH BÁO: đang mở ra mạng LAN nhưng PIN vẫn là 1234, hãy đổi trong config.json.")

    app = create_app(args.dry_run, cfg)
    if args.web:
        uvicorn.run(app, host=cfg["host"], port=cfg["port"], log_level="warning")
        return
    server = uvicorn.Server(uvicorn.Config(app, host=cfg["host"], port=cfg["port"], log_level="warning"))
    run_desktop(server, base, cfg["pin"])


if __name__ == "__main__":
    main()
