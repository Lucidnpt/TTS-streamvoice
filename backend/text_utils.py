"""Chuẩn hóa văn bản và chia thành các đoạn ngắn để phát sớm, phụ đề từng câu."""
import re

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SENT_END = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE = re.compile(r"(?<=[,;:])\s+")


def normalize(text, max_chars=400):
    """Bỏ ký tự điều khiển, gộp khoảng trắng, cắt theo độ dài tối đa."""
    text = " ".join(_CONTROL.sub(" ", text).split())
    return text[:max_chars].strip()


def split_segments(text, max_chars=140):
    """Chia theo câu; câu quá dài thì chia tiếp theo dấu phẩy, cuối cùng theo từ."""
    pieces = []
    for sentence in _SENT_END.split(text):
        sentence = sentence.strip()
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        buf = ""
        for part in _CLAUSE.split(sentence):
            if buf and len(buf) + 1 + len(part) > max_chars:
                pieces.append(buf)
                buf = part
            else:
                buf = f"{buf} {part}".strip()
        pieces.append(buf)

    segments = []
    for piece in pieces:
        while len(piece) > max_chars:                 # không có dấu phẩy: cắt theo từ
            cut = piece.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            segments.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            segments.append(piece)
    return segments


if __name__ == "__main__":      # python -m backend.text_utils
    demo = "Hello everyone, welcome to my stream! Thanks for the follow. " + "This is a very long sentence, " * 8
    for seg in split_segments(normalize(demo)):
        print(f"{len(seg):>4} | {seg}")
