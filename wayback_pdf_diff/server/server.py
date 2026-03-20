"""
HTTP server for PDF diffs.

Mirrors the API contract of web-monitoring-diff's server:
    GET /<diff_type>?a=<url>&b=<url>

Start it the same way::

    wayback-pdf-diff --port 8889

Or from Python::

    from wayback_pdf_diff.server import start_app
    start_app(8889)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import inspect
import logging
import os
import signal as signal_mod
import sys
from argparse import ArgumentParser

import tornado.httpclient
import tornado.ioloop
import tornado.web

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

import wayback_pdf_diff
from ..routes import DIFF_ROUTES

logger = logging.getLogger(__name__)

DIFFER_PARALLELISM = int(os.environ.get("DIFFER_PARALLELISM", 4))

access_control_allow_origin_header = os.environ.get(
    "ACCESS_CONTROL_ALLOW_ORIGIN_HEADER"
)

DEBUG_MODE = (
    os.environ.get("DIFFING_SERVER_DEBUG", "False").strip().lower() == "true"
)

VALIDATE_TARGET_CERTIFICATES = (
    os.environ.get("VALIDATE_TARGET_CERTIFICATES", "False").strip().lower()
    == "true"
)


tornado.httpclient.AsyncHTTPClient.configure(None)


def _get_http_client() -> tornado.httpclient.AsyncHTTPClient:
    return tornado.httpclient.AsyncHTTPClient()


class PublicError(tornado.web.HTTPError):
    def __init__(
        self,
        status_code: int = 500,
        public_message: str | None = None,
        log_message: str | None = None,
        extra: dict | None = None,
        **kwargs,
    ):
        self.extra = extra or {}
        if public_message is not None:
            self.extra.setdefault("error", public_message)
            if log_message is None:
                log_message = public_message
        super().__init__(status_code, log_message, **kwargs)


def _caller(func, a_response, b_response, **query_params):
    """
    Translation layer between HTTP responses and diff functions.

    Uses the same dependency-injection convention as web-monitoring-diff:
    argument names ``a_body`` / ``b_body`` are mapped to the raw response
    bodies (bytes).
    """
    query_params.setdefault("a_body", a_response.body)
    query_params.setdefault("b_body", b_response.body)
    query_params.setdefault("a_headers", a_response.headers)
    query_params.setdefault("b_headers", b_response.headers)

    sig = inspect.signature(func)
    kwargs: dict = {}
    for name, param in sig.parameters.items():
        if name == "dpi":
            kwargs[name] = int(query_params.get("dpi", 150))
            continue
        try:
            kwargs[name] = query_params[name]
        except KeyError:
            if param.default is inspect.Parameter.empty:
                raise KeyError(
                    f"{func.__name__} requires parameter '{name}' "
                    f"which was not provided"
                )
    return func(**kwargs)


class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        allowed_origins = access_control_allow_origin_header
        if allowed_origins is None:
            allowed_origins = "*"

        if "allowed_origins" not in self.settings:
            self.settings["allowed_origins"] = {
                o.strip() for o in allowed_origins.split(",")
            }
        req_origin = self.request.headers.get("Origin")
        if req_origin:
            allowed = self.settings.get("allowed_origins")
            if allowed and (req_origin in allowed or "*" in allowed):
                self.set_header("Access-Control-Allow-Origin", req_origin)
        elif "*" in self.settings.get("allowed_origins", set()):
            self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Credentials", "true")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def options(self, *args):
        self.set_status(204)
        self.finish()

    def write_error(self, status_code, **kwargs):
        response: dict = {"code": status_code}
        actual_error = kwargs.get("exc_info", (None, None, None))[1]
        if isinstance(actual_error, PublicError):
            response.update(actual_error.extra)
        elif actual_error:
            response["error"] = str(actual_error)
        if self.settings.get("serve_traceback") and "exc_info" in kwargs:
            import traceback

            response["stack"] = "".join(
                traceback.format_exception(*kwargs["exc_info"])
            )
        if response["code"] != status_code:
            self.set_status(response["code"])
        self.finish(response)


class DiffHandler(BaseHandler):
    differs: dict = DIFF_ROUTES

    async def get(self, differ: str):
        try:
            func = self.differs[differ]
        except KeyError:
            raise PublicError(
                404,
                f"Unknown diff type: '{differ}'. "
                f"Supported: {', '.join(self.differs)}",
            )

        query_params = {
            k: v[-1].decode() for k, v in self.request.arguments.items()
        }

        try:
            urls = {p: query_params.pop(p) for p in ("a", "b")}
        except KeyError:
            raise PublicError(
                400, "Must provide both 'a' and 'b' query parameters as URLs."
            )

        a_hash = query_params.pop("a_hash", None)
        b_hash = query_params.pop("b_hash", None)

        requests = [
            self._fetch(url, expected_hash)
            for url, expected_hash in zip(urls.values(), (a_hash, b_hash))
        ]
        try:
            content = await asyncio.gather(*requests)
        except PublicError:
            raise
        except Exception as exc:
            raise PublicError(502, f"Failed fetching upstream content: {exc}")

        executor = self._get_executor()
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                executor,
                functools.partial(
                    _caller, func, content[0], content[1], **query_params
                ),
            )
        except Exception as exc:
            logger.exception("Diff failed")
            raise PublicError(500, f"Diff computation failed: {exc}")

        # Attach version and type for web-monitoring-diff compatibility.
        result["version"] = wayback_pdf_diff.__version__
        result.setdefault("type", differ)

        self.write(result)

    async def _fetch(
        self, url: str, expected_hash: str | None = None
    ) -> tornado.httpclient.HTTPResponse:
        if url.startswith("file://"):
            if os.environ.get("WEB_MONITORING_APP_ENV") == "production":
                raise PublicError(403, "file:// URLs disabled in production")
            with open(url[7:], "rb") as f:
                body = f.read()
            return _MockResponse(url, body)

        if not url.startswith(("http://", "https://")):
            raise PublicError(400, f"URL must use HTTP or HTTPS: '{url}'")

        headers = {"User-Agent": "Mozilla/5.0 (compatible; wayback-pdf-diff/1.0)"}
        header_keys = self.request.headers.get("pass_headers")
        if header_keys:
            for hk in header_keys.split(","):
                hk = hk.strip()
                hv = self.request.headers.get(hk)
                if hv:
                    headers[hk] = hv

        try:
            client = _get_http_client()
            response = await client.fetch(
                url,
                headers=headers,
                validate_cert=VALIDATE_TARGET_CERTIFICATES,
                request_timeout=120.0,
            )
        except tornado.httpclient.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.headers.get("Memento-Datetime") is not None
            ):
                response = exc.response
            else:
                code = exc.response.code if exc.response else "?"
                raise PublicError(
                    502,
                    f"Received {code} fetching '{url}': {exc}",
                )
        except Exception as exc:
            raise PublicError(502, f"Could not fetch '{url}': {exc}")

        if expected_hash:
            import hashlib

            actual = hashlib.sha256(response.body).hexdigest()
            if actual != expected_hash:
                raise PublicError(
                    502,
                    f"Content at '{url}' does not match hash '{expected_hash}'",
                )

        return response

    def _get_executor(self) -> concurrent.futures.ProcessPoolExecutor:
        executor = self.settings.get("diff_executor")
        if executor is None or executor._broken:
            executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=DIFFER_PARALLELISM
            )
            self.settings["diff_executor"] = executor
        return executor


class _MockRequest:
    def __init__(self, url: str):
        self.url = url


class _MockResponse:
    def __init__(self, url: str, body: bytes):
        self.request = _MockRequest(url)
        self.body = body
        self.headers = {}


class ProxyHandler(BaseHandler):
    """Proxy a remote URL back to the browser.

    ``GET /pdf_proxy?url=<encoded-url>``

    Fetches the target URL server-side (reusing the same fetch logic as
    ``DiffHandler``) and streams the raw bytes to the browser with the
    original ``Content-Type``.  Allows the frontend PDF.js viewer to load
    PDFs from arbitrary origins without CORS issues.
    """

    async def get(self):
        url = self.get_argument("url", None)
        if not url:
            raise PublicError(400, "Must provide 'url' query parameter")
        if not url.startswith(("http://", "https://", "file://")):
            raise PublicError(400, f"URL must use HTTP, HTTPS, or file://: '{url}'")

        if url.startswith("file://"):
            if os.environ.get("WEB_MONITORING_APP_ENV") == "production":
                raise PublicError(403, "file:// URLs disabled in production")
            with open(url[7:], "rb") as fh:
                body = fh.read()
            self.set_header("Content-Type", "application/pdf")
            self.write(body)
            return

        headers = {"User-Agent": "Mozilla/5.0 (compatible; wayback-pdf-diff/1.0)"}
        try:
            client = _get_http_client()
            response = await client.fetch(
                url,
                headers=headers,
                validate_cert=VALIDATE_TARGET_CERTIFICATES,
                request_timeout=120.0,
            )
        except tornado.httpclient.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.headers.get("Memento-Datetime") is not None
            ):
                response = exc.response
            else:
                code = exc.response.code if exc.response else "?"
                raise PublicError(502, f"Received {code} fetching '{url}': {exc}")
        except Exception as exc:
            raise PublicError(502, f"Could not fetch '{url}': {exc}")

        content_type = response.headers.get("Content-Type", "application/pdf")
        self.set_header("Content-Type", content_type)
        self.write(response.body)


class ViewerHandler(BaseHandler):
    """Serve the PDF diff viewer HTML page.

    ``GET /viewer?a=<url>&b=<url>``

    The HTML page is self-contained; query parameters are forwarded as-is
    so the browser-side JavaScript can pick them up via ``location.search``.
    """

    async def get(self):
        viewer_path = os.path.join(_STATIC_DIR, "viewer.html")
        with open(viewer_path, "rb") as fh:
            self.set_header("Content-Type", "text/html; charset=utf-8")
            self.write(fh.read())


class IndexHandler(BaseHandler):
    async def get(self):
        self.write(
            {
                "diff_types": list(DIFF_ROUTES),
                "version": wayback_pdf_diff.__version__,
            }
        )


class HealthCheckHandler(BaseHandler):
    async def get(self):
        self.write({})


def make_app() -> tornado.web.Application:
    return tornado.web.Application(
        [
            (r"/healthcheck", HealthCheckHandler),
            (r"/pdf_proxy", ProxyHandler),
            (r"/viewer", ViewerHandler),
            (r"/([A-Za-z0-9_]+)", DiffHandler),
            (r"/", IndexHandler),
        ],
        debug=DEBUG_MODE,
        compress_response=True,
        diff_executor=None,
    )


def start_app(port: int) -> None:
    app = make_app()
    print(f"Starting wayback-pdf-diff server on port {port}")
    app.listen(port)

    def _handle_signal(sig, frame):
        print("\nShutting down...")
        tornado.ioloop.IOLoop.current().stop()

    signal_mod.signal(signal_mod.SIGINT, _handle_signal)
    signal_mod.signal(signal_mod.SIGTERM, _handle_signal)
    tornado.ioloop.IOLoop.current().start()


def cli() -> None:
    parser = ArgumentParser(description="Start the PDF diff server.")
    parser.add_argument(
        "--version", action="store_true", help="Show version and exit"
    )
    parser.add_argument(
        "--port", type=int, default=8889, help="Port to listen on (default: 8889)"
    )
    args = parser.parse_args()

    if args.version:
        print(wayback_pdf_diff.__version__)
        return

    start_app(args.port)


if __name__ == "__main__":
    cli()
