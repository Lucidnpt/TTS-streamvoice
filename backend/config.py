"""Đọc/ghi config.json; khóa nào thiếu thì dùng giá trị mặc định."""
import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULT_PHRASES = [
    {"label": "Thanks!", "text": "Thank you so much for the follow!", "hotkey": "ctrl+alt+1"},
    {"label": "Welcome", "text": "Welcome to the stream, everyone.", "hotkey": "ctrl+alt+2"},
    {"label": "One sec", "text": "Give me one second, I will be right back.", "hotkey": "ctrl+alt+3"},
    {"label": "Good game", "text": "Good game, well played everyone.", "hotkey": "ctrl+alt+4"},
]
DEFAULT_STOP_HOTKEY = "ctrl+alt+s"

DEFAULT_OVERLAY = {
    "font_size": 44,
    "font_family": "Segoe UI",
    "color": "#ffffff",
    "outline_color": "#000000",
    "position": "bottom",         # "bottom" | "top"
}

DEFAULTS = {
    "host": "127.0.0.1",          # đổi thành "0.0.0.0" nếu muốn mở control panel từ điện thoại
    "port": 8765,
    "pin": "1234",                # ĐỔI mã này nếu mở ra mạng LAN
    "model_path": "voices/en_US-lessac-medium.onnx",
    "output_device": "CABLE Input",   # số thứ tự, một phần tên thiết bị, hoặc null = loa mặc định
    "speed": 1.0,                 # >1 nói nhanh hơn
    "max_chars": 400,             # giới hạn độ dài một lần nói
    "max_queue": 5,               # số lệnh tối đa xếp hàng chờ
    "log_latency": True,          # ghi logs/latency.csv để làm số liệu cho báo cáo
    "phrases": DEFAULT_PHRASES,
    "stop_hotkey": DEFAULT_STOP_HOTKEY,
    "hotkeys_enabled": True,
    "overlay": DEFAULT_OVERLAY,
}

# Các khóa người dùng chỉnh được từ giao diện cài đặt.
SETTINGS_KEYS = ("phrases", "stop_hotkey", "hotkeys_enabled", "overlay")


def load_config(path=None):
    path = Path(path) if path else CONFIG_PATH
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        overlay = data.pop("overlay", None)
        cfg.update(data)
        if isinstance(overlay, dict):
            cfg["overlay"].update(overlay)
    cfg["config_path"] = str(path)
    model = Path(cfg["model_path"])
    if not model.is_absolute():
        cfg["model_path"] = str(ROOT / model)
    return cfg


def save_settings(path, updates):
    """Ghi các khóa cài đặt vào file JSON gốc, giữ nguyên mọi khóa khác (vd. model_path tương đối)."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for key in SETTINGS_KEYS:
        if key in updates:
            data[key] = updates[key]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
