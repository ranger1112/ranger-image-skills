from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "ranger-image-2" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ranger_image_lib.api import post_json
from ranger_image_lib.config import derive_base_url
from ranger_image_lib.cli import PRESET_SIZES, resolve_size
from ranger_image_lib.output import normalize_image_response, output_path_for_index, url_sidecar_path_for_out
import generate_image


class ConfigTests(unittest.TestCase):
    def test_derive_base_url_from_custom_api_path(self) -> None:
        self.assertEqual(
            derive_base_url("https://host.example/api/image/generate", None),
            "https://host.example/v1",
        )

    def test_derive_base_url_keeps_explicit_v1(self) -> None:
        self.assertEqual(
            derive_base_url(None, "https://host.example/v1/"),
            "https://host.example/v1",
        )


class ResponseNormalizationTests(unittest.TestCase):
    def test_normalize_supported_response_shapes(self) -> None:
        raw = b"fake-image"
        b64 = base64.b64encode(raw).decode("ascii")
        cases = [
            ({"data": [{"b64_json": b64}]}, "base64", raw),
            ({"data": [{"base64": b64}]}, "base64", raw),
            ({"data": [{"url": "data:image/png;base64," + b64}]}, "base64", raw),
            (raw, "base64", raw),
        ]
        for payload, kind, expected in cases:
            with self.subTest(payload=type(payload).__name__):
                entry = normalize_image_response(payload)[0]
                self.assertEqual(entry["kind"], kind)
                self.assertEqual(base64.b64decode(entry["value"]), expected)

    def test_normalize_url_response(self) -> None:
        entry = normalize_image_response({"data": [{"url": "https://example.com/image.png"}]})[0]
        self.assertEqual(entry["kind"], "url")
        self.assertEqual(entry["value"], "https://example.com/image.png")

    def test_multi_output_naming(self) -> None:
        base = Path("output/imagegen/demo.png")
        self.assertEqual(output_path_for_index(base, 0, 3).name, "demo.png")
        self.assertEqual(output_path_for_index(base, 1, 3).name, "demo-2.png")
        self.assertEqual(url_sidecar_path_for_out(base).name, "demo.png.url.txt")


class RawHttpTests(unittest.TestCase):
    def test_post_json_wraps_direct_binary_response(self) -> None:
        binary = bytes([0x89, 0x50, 0x4E, 0x47, 0xFF, 0xFE])
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                seen["path"] = self.path
                seen["auth"] = self.headers.get("authorization")
                _ = self.rfile.read(int(self.headers.get("content-length", "0")))
                self.send_response(200)
                self.send_header("content-type", "image/png")
                self.send_header("content-length", str(len(binary)))
                self.end_headers()
                self.wfile.write(binary)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = post_json(
                key="dummy",
                url=f"http://127.0.0.1:{server.server_port}/v1/images/generations",
                payload={"model": "gpt-image-2", "prompt": "x"},
                timeout=30,
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual(seen["path"], "/v1/images/generations")
        self.assertEqual(seen["auth"], "Bearer dummy")
        entry = normalize_image_response(result)[0]
        self.assertEqual(base64.b64decode(entry["value"]), binary)


class PresetAndCliTests(unittest.TestCase):
    def test_preset_sizes(self) -> None:
        self.assertEqual(PRESET_SIZES["4k-landscape"], "3840x2160")
        self.assertEqual(resolve_size(None, "4k-portrait"), "2160x3840")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                resolve_size("1024x1024", "square")
            with self.assertRaises(SystemExit):
                resolve_size("wide", None)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = "dummy"
        env["OPENAI_BASE_URL"] = "https://example.com/v1"
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "generate_image.py"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_generate_dry_run_preview(self) -> None:
        result = self.run_cli("--prompt", "x", "--out", "output/imagegen/x.png", "--preset", "4k-landscape", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["endpoint"], "/v1/images/generations")
        self.assertEqual(payload["size"], "3840x2160")

    def test_edit_url_dry_run_preview(self) -> None:
        result = self.run_cli(
            "--edit",
            "--image-url",
            "https://example.com/source.png",
            "--prompt",
            "x",
            "--out",
            "output/imagegen/edit.png",
            "--no-download-url",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["endpoint"], "/v1/images/edits")
        self.assertTrue(payload["no_download_url"])

    def test_no_download_url_writes_sidecar(self) -> None:
        url = "https://example.com/generated.png"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.png"
            out.write_bytes(b"existing-local-image")
            code = (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(SCRIPTS)!r}); "
                "from ranger_image_lib.cli import build_parser, validate_common_args, save_image_entries; "
                "parser=build_parser(); "
                f"args=parser.parse_args(['--prompt','x','--out',{str(out)!r},'--no-download-url']); "
                "validate_common_args(args); "
                f"save_image_entries([{{'index':0,'kind':'url','value':{url!r}}}], Path({str(out)!r}), args)"
            )
            result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(out.read_bytes(), b"existing-local-image")
            self.assertEqual((Path(str(out) + ".url.txt")).read_text(encoding="utf-8").strip(), url)

    def test_no_download_url_cli_preserves_existing_out(self) -> None:
        generated_url = "https://example.com/generated.png"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.dumps({"data": [{"url": generated_url}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "result.png"
                out.write_bytes(b"existing-local-image")
                env = os.environ.copy()
                env["OPENAI_API_KEY"] = "dummy"
                env["OPENAI_BASE_URL"] = f"http://127.0.0.1:{server.server_port}/v1"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "generate_image.py"),
                        "--prompt",
                        "x",
                        "--out",
                        str(out),
                        "--response-format",
                        "url",
                        "--no-download-url",
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(out.read_bytes(), b"existing-local-image")
                self.assertEqual((Path(str(out) + ".url.txt")).read_text(encoding="utf-8").strip(), generated_url)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_no_download_url_existing_sidecar_fails_before_api_call(self) -> None:
        api_calls = {"count": 0}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                api_calls["count"] += 1
                payload = json.dumps({"data": [{"url": "https://example.com/generated.png"}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "result.png"
                Path(str(out) + ".url.txt").write_text("existing\n", encoding="utf-8")
                env = os.environ.copy()
                env["OPENAI_API_KEY"] = "dummy"
                env["OPENAI_BASE_URL"] = f"http://127.0.0.1:{server.server_port}/v1"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "generate_image.py"),
                        "--prompt",
                        "x",
                        "--out",
                        str(out),
                        "--response-format",
                        "url",
                        "--no-download-url",
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Output already exists", result.stderr)
                self.assertEqual(api_calls["count"], 0)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_generate_image_wrapper_reexports_legacy_helpers(self) -> None:
        self.assertIs(generate_image.extract_image_entries, normalize_image_response)
        self.assertEqual(generate_image.derive_base_url(None, "https://example.com/v1/"), "https://example.com/v1")
        self.assertEqual(generate_image.output_path_for_index(Path("demo.png"), 1, 2).name, "demo-2.png")


if __name__ == "__main__":
    unittest.main()
