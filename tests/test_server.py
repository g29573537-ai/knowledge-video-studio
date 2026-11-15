import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from narration_video.server import MediaHandler


def test_real_http_media_ranges_and_head(tmp_path):
    payload = bytes(range(256)) * 4
    (tmp_path / "audio.wav").write_bytes(payload)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(MediaHandler, directory=str(tmp_path))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/audio.wav"
    try:
        for spec, expected in [
            ("bytes=0-1", payload[:2]),
            ("bytes=100-199", payload[100:200]),
            ("bytes=1000-", payload[1000:]),
            ("bytes=-12", payload[-12:]),
        ]:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"Range": spec})
            ) as result:
                assert result.status == 206
                assert result.read() == expected
                assert result.headers["Accept-Ranges"] == "bytes"
        with urllib.request.urlopen(
            urllib.request.Request(url, method="HEAD", headers={"Range": "bytes=4-6"})
        ) as result:
            assert (
                result.status == 206
                and result.headers["Content-Length"] == "3"
                and result.read() == b""
            )
        for spec in ["bytes=2048-", "bytes=8-2", "bytes=-0", "bytes=", "bytes=1-2,5-8"]:
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(
                    urllib.request.Request(url, headers={"Range": spec})
                )
            assert error.value.code == 416
        with urllib.request.urlopen(url) as result:
            assert result.read() == payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
