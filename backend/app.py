"""FastAPI: WebSocket cho control/overlay, REST cho phím tắt, phục vụ 2 trang web."""
import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from typing import List, Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import hotkeys as hk
from .audio_out import NullSink, SoundDeviceSink
from .config import DEFAULT_OVERLAY, DEFAULT_PHRASES, DEFAULT_STOP_HOTKEY, ROOT, load_config, save_settings
from .speaker import Speaker
from .tts_engine import FakeEngine, PiperEngine

WEB = ROOT / "web"
MESSAGES = {
    "queue_full": "Hàng đợi đầy, hãy đợi hoặc nhấn Dừng.",
    "empty": "Chưa có nội dung để nói.",
}


class SpeakBody(BaseModel):
    text: str


class Phrase(BaseModel):
    label: str = Field("", max_length=60)
    text: str = Field(..., min_length=1, max_length=400)
    hotkey: str = Field("", max_length=60)


class OverlayStyle(BaseModel):
    font_size: int = Field(44, ge=12, le=200)
    font_family: str = Field("Segoe UI", min_length=1, max_length=60, pattern=r"^[^;{}<>\"]+$")
    color: str = Field("#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    outline_color: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    position: Literal["top", "bottom"] = "bottom"


class Settings(BaseModel):
    phrases: List[Phrase] = Field(default_factory=list, max_length=50)
    stop_hotkey: str = Field("", max_length=60)
    hotkeys_enabled: bool = True
    overlay: OverlayStyle = Field(default_factory=OverlayStyle)


class Hub:
    """Các trang đang kết nối (control + overlay); gửi một sự kiện cho tất cả."""

    def __init__(self):
        self.clients = set()

    async def broadcast(self, event):
        data = json.dumps(event, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                self.clients.discard(ws)


def create_app(dry_run=False, cfg=None):
    cfg = cfg or load_config()
    hub = Hub()
    box = {}

    def pin_ok(pin):
        return secrets.compare_digest(str(pin).encode(), str(cfg["pin"]).encode())

    @asynccontextmanager
    async def lifespan(app):
        loop = asyncio.get_running_loop()

        def quiet(loop_, context):  # Windows: trình duyệt/cửa sổ app đóng đột ngột -> lỗi vô hại
            if isinstance(context.get("exception"), ConnectionResetError):
                return
            loop_.default_exception_handler(context)
        loop.set_exception_handler(quiet)

        def emit(event):    # gọi từ các luồng TTS -> chuyển sang event loop để gửi qua WebSocket
            try:
                asyncio.run_coroutine_threadsafe(hub.broadcast(event), loop)
            except RuntimeError:
                pass        # đang tắt server

        if dry_run:
            engine, sink = FakeEngine(), NullSink()
            print("Chế độ chạy thử (--dry-run): không dùng Piper, không phát ra loa.")
        else:
            engine = PiperEngine(cfg["model_path"], cfg["speed"])
            sink = SoundDeviceSink(cfg["output_device"])
            print(f"Đã nạp model trong {engine.load_seconds:.1f}s, sample rate {engine.sample_rate} Hz")
        log_path = ROOT / "logs" / "latency.csv" if cfg["log_latency"] else None
        box["speaker"] = Speaker(engine, sink, emit, cfg["max_queue"], cfg["max_chars"], log_path)
        box["hotkeys"] = hk.HotkeyManager(box["speaker"])
        box["hotkeys"].apply(cfg["phrases"], cfg["stop_hotkey"], cfg["hotkeys_enabled"])
        yield
        box["hotkeys"].clear()
        box["speaker"].close()

    app = FastAPI(lifespan=lifespan)

    # ---- trang web -------------------------------------------------------------
    @app.get("/")
    def index():
        return RedirectResponse("/control")

    @app.get("/control")
    def control_page():
        return FileResponse(WEB / "control.html")

    @app.get("/overlay")
    def overlay_page():
        return FileResponse(WEB / "overlay.html")

    # ---- REST (cho phím tắt toàn cục) --------------------------------------------
    def check_pin(x_pin):
        if not pin_ok(x_pin):
            raise HTTPException(401, "Sai mã PIN")

    @app.post("/api/speak")
    def api_speak(body: SpeakBody, x_pin: str = Header(default="")):
        check_pin(x_pin)
        ok, info = box["speaker"].submit(body.text)
        if not ok:
            raise HTTPException(429 if info == "queue_full" else 400, MESSAGES[info])
        return {"ok": True, "job": info}

    @app.post("/api/stop")
    def api_stop(x_pin: str = Header(default="")):
        check_pin(x_pin)
        box["speaker"].stop()
        return {"ok": True}

    # ---- cài đặt -------------------------------------------------------------------
    def current_settings():
        return {key: cfg[key] for key in ("phrases", "stop_hotkey", "hotkeys_enabled", "overlay")}

    @app.get("/api/settings")
    def get_settings(x_pin: str = Header(default="")):
        check_pin(x_pin)
        return {**current_settings(), "hotkeys_available": box["hotkeys"].available,
                "defaults": {"phrases": DEFAULT_PHRASES, "stop_hotkey": DEFAULT_STOP_HOTKEY,
                             "overlay": DEFAULT_OVERLAY}}

    @app.put("/api/settings")
    async def put_settings(body: Settings, x_pin: str = Header(default="")):
        check_pin(x_pin)
        data = body.model_dump()
        for p in data["phrases"]:
            p["label"], p["text"] = p["label"].strip(), p["text"].strip()
            p["hotkey"] = hk.normalize_hotkey(p["hotkey"])
        data["stop_hotkey"] = hk.normalize_hotkey(data["stop_hotkey"])
        data["overlay"]["font_family"] = data["overlay"]["font_family"].strip()

        if any(not p["text"] for p in data["phrases"]):
            raise HTTPException(400, "Có câu nói nhanh đang để trống nội dung.")
        seen = {}
        named = [(p["hotkey"], p["label"] or p["text"][:20]) for p in data["phrases"]]
        named.append((data["stop_hotkey"], "Dừng"))
        for key, who in named:
            if not key:
                continue
            err = hk.validate(key)
            if err:
                raise HTTPException(400, err)
            if key in seen:
                raise HTTPException(400, f"Phím '{key}' bị trùng giữa '{seen[key]}' và '{who}'.")
            seen[key] = who

        save_settings(cfg["config_path"], data)
        cfg.update(data)
        errors = box["hotkeys"].apply(cfg["phrases"], cfg["stop_hotkey"], cfg["hotkeys_enabled"])
        await hub.broadcast({"type": "phrases", "phrases": cfg["phrases"]})
        await hub.broadcast({"type": "overlay_style", **cfg["overlay"]})
        return {"ok": True, "warnings": errors, **current_settings()}

    # ---- WebSocket ----------------------------------------------------------------
    @app.websocket("/ws/overlay")
    async def ws_overlay(ws: WebSocket):
        await ws.accept()
        await ws.send_text(json.dumps({"type": "overlay_style", **cfg["overlay"]}, ensure_ascii=False))
        hub.clients.add(ws)
        try:
            while True:
                await ws.receive_text()     # overlay chỉ nhận; mọi thứ nó gửi đều bị bỏ qua
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    @app.websocket("/ws/control")
    async def ws_control(ws: WebSocket):
        await ws.accept()
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
        except Exception:
            await ws.close(code=4400)
            return
        if first.get("type") != "auth" or not pin_ok(first.get("pin", "")):
            await ws.send_text(json.dumps({"type": "auth_failed"}))
            await ws.close(code=4401)
            return
        speaker = box["speaker"]
        await ws.send_text(json.dumps({"type": "ready", "phrases": cfg["phrases"]}, ensure_ascii=False))
        await ws.send_text(json.dumps(speaker.status()))
        hub.clients.add(ws)
        try:
            while True:
                try:
                    msg = json.loads(await ws.receive_text())
                except ValueError:
                    continue
                if msg.get("type") == "speak":
                    ok, info = speaker.submit(str(msg.get("text", "")))
                    if not ok:
                        err = {"type": "error", "message": MESSAGES[info]}
                        await ws.send_text(json.dumps(err, ensure_ascii=False))
                elif msg.get("type") == "stop":
                    speaker.stop()
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    return app
