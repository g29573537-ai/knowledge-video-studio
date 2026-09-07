"""Local preview with byte ranges required for reliable media seeking in WebKit."""

import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class MediaHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.remaining = None
        path = Path(self.translate_path(self.path))
        value = self.headers.get("Range")
        if not value or not path.is_file():
            return super().send_head()
        try:
            stream = path.open("rb")
        except OSError:
            self.send_error(404)
            return None
        size = path.stat().st_size
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
        start, end = 0, size - 1
        valid = bool(match and any(match.groups()) and size)
        if valid:
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(int(right), end) if right else end
            else:
                start = max(0, size - int(right))
            valid = 0 <= start <= end < size
        if not valid:
            stream.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.remaining = end - start + 1
        stream.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(self.remaining))
        self.end_headers()
        return stream

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def copyfile(self, source, outputfile):
        if self.remaining is None:
            return super().copyfile(source, outputfile)
        while self.remaining:
            chunk = source.read(min(self.remaining, 65536))
            if not chunk:
                break
            outputfile.write(chunk)
            self.remaining -= len(chunk)


def serve(root: Path, port: int):
    with ThreadingHTTPServer(
        ("127.0.0.1", port), partial(MediaHandler, directory=str(root))
    ) as server:
        print(f"PREVIEW http://127.0.0.1:{port}/ (Ctrl-C to stop)", flush=True)
        server.serve_forever()
