"""FastAPI: WebSocket cho control/overlay, REST cho phím tắt, phục vụ 2 trang web."""
import asyncio
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from .audio_out import NullSink, SoundDeviceSink
from .config import ROOT, load_config
from .speaker import Speaker
from .tts_engine import FakeEngine, PiperEngine

WEB = ROOT / "web"
MESSAGES = {
    "queue_full": "Hàng đợi đầy, hãy đợi hoặc nhấn Dừng.",
    "empty": "Chưa có nội dung để nói.",
}


class SpeakBody(BaseModel):
    text: str


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
        yield
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

    # ---- WebSocket ----------------------------------------------------------------
    @app.websocket("/ws/overlay")
    async def ws_overlay(ws: WebSocket):
        await ws.accept()
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
