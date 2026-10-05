"""
Now Playing — маленький помощник для домашней страницы.

Спрашивает у Windows, что сейчас играет (та же медиа-панель, что показывает
название при смене громкости), и отдаёт это странице по адресу
http://127.0.0.1:8765  — только с твоего компьютера, наружу ничего не уходит.

Установка (один раз, в терминале):
    pip install winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media.Control winrt-Windows.Storage.Streams

Запуск для проверки:
    python nowplaying.py
"""

import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
)
from winrt.windows.storage.streams import Buffer, InputStreamOptions

HOST = "127.0.0.1"
PORT = 8765
POLL_SECONDS = 1.0
HERE = os.path.dirname(os.path.abspath(__file__))

PLAYING = 4  # значение статуса "играет" в Windows

lock = threading.Lock()
state = {
    "active": False,
    "title": "",
    "artist": "",
    "album": "",
    "playing": False,
    "position": 0.0,   # секунд
    "duration": 0.0,   # секунд, 0 — неизвестно
    "updated": 0.0,    # когда замерили позицию (unix-время)
    "cover": 0,        # номер обложки, меняется вместе с треком
    "has_cover": False,
}
cover_bytes = b""


async def read_thumbnail(ref):
    stream = await ref.open_read_async()
    size = stream.size
    if not size:
        return b""
    buf = Buffer(size)
    await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
    return bytes(memoryview(buf))


async def poll():
    global cover_bytes
    manager = await MediaManager.request_async()
    last_key = None

    while True:
        try:
            session = manager.get_current_session()
            if session is None:
                with lock:
                    state["active"] = False
                    state["playing"] = False
            else:
                info = await session.try_get_media_properties_async()
                playback = session.get_playback_info()
                timeline = session.get_timeline_properties()

                key = (
                    info.title,
                    info.artist,
                    info.album_title,
                    session.source_app_user_model_id,
                )
                if key != last_key:
                    last_key = key
                    data = b""
                    if info.thumbnail:
                        try:
                            data = await read_thumbnail(info.thumbnail)
                        except Exception:
                            data = b""
                    with lock:
                        cover_bytes = data
                        state["cover"] += 1
                        state["has_cover"] = bool(data)

                try:
                    duration = (timeline.end_time - timeline.start_time).total_seconds()
                    position = timeline.position.total_seconds()
                except Exception:
                    duration, position = 0.0, 0.0

                with lock:
                    state.update(
                        active=bool(info.title or info.artist),
                        title=info.title or "",
                        artist=info.artist or "",
                        album=info.album_title or "",
                        playing=int(playback.playback_status) == PLAYING,
                        position=max(position, 0.0),
                        duration=max(duration, 0.0),
                        updated=time.time(),
                    )
        except Exception:
            with lock:
                state["active"] = False
        await asyncio.sleep(POLL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # без шума в консоли

    def _send(self, code, body, ctype):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, OSError):
            pass

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/now":
            with lock:
                body = json.dumps(state).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

        elif path == "/cover":
            with lock:
                data = cover_bytes
            if not data:
                self._send(404, b"", "text/plain")
            else:
                ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
                self._send(200, data, ctype)

        elif path in ("/", "/home.html"):
            # Запасной вариант: страница рядом со скриптом открывается прямо отсюда
            try:
                with open(os.path.join(HERE, "home.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(404, b"home.html not found", "text/plain")

        else:
            self._send(404, b"", "text/plain")


def serve():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    print(f"Now Playing работает: http://{HOST}:{PORT}/now  (Ctrl+C — выйти)")
    try:
        asyncio.run(poll())
    except KeyboardInterrupt:
        pass
