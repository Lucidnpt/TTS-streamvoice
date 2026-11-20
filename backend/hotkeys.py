"""Phím tắt toàn cục (chạy trong cùng tiến trình với server): bấm tổ hợp phím, kể cả khi
đang chơi game, để nói câu nhanh hoặc dừng."""

try:
    import keyboard
except Exception as exc:          # thiếu thư viện / không có quyền hook bàn phím
    keyboard = None
    _IMPORT_ERROR = exc


def normalize_hotkey(hotkey):
    return "+".join(p.strip() for p in str(hotkey or "").lower().split("+") if p.strip())


def validate(hotkey):
    """Trả None nếu hợp lệ, ngược lại trả thông báo lỗi."""
    if keyboard is None:
        return None               # không kiểm tra được; apply() sẽ bỏ qua
    try:
        keyboard.parse_hotkey(hotkey)
        return None
    except Exception:
        return f"Tổ hợp phím không hợp lệ: '{hotkey}'"


class HotkeyManager:
    def __init__(self, speaker):
        self.speaker = speaker
        self.available = keyboard is not None
        if not self.available:
            print(f"Không dùng được phím tắt toàn cục ({_IMPORT_ERROR}).")

    def apply(self, phrases, stop_hotkey, enabled):
        """Gỡ toàn bộ phím tắt cũ rồi đăng ký lại theo cài đặt mới. Trả danh sách lỗi."""
        if not self.available:
            return []
        self.clear()
        if not enabled:
            return []
        errors = []
        bindings = [(p.get("hotkey"), self.speaker.submit, (p.get("text", ""),)) for p in phrases]
        bindings.append((stop_hotkey, self.speaker.stop, ()))
        for hotkey, fn, args in bindings:
            hotkey = normalize_hotkey(hotkey)
            if not hotkey:
                continue
            try:
                keyboard.add_hotkey(hotkey, fn, args=args)
            except Exception as exc:
                errors.append(f"{hotkey}: {exc}")
        for err in errors:
            print("Lỗi phím tắt:", err)
        return errors

    def clear(self):
        if self.available:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
