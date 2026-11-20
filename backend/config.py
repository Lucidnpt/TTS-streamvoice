"""Đọc config.json; khóa nào thiếu thì dùng giá trị mặc định."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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
    "phrases": [],
    "stop_hotkey": "",
}


def load_config(path=None):
    path = Path(path) if path else ROOT / "config.json"
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    model = Path(cfg["model_path"])
    if not model.is_absolute():
        cfg["model_path"] = str(ROOT / model)
    return cfg
