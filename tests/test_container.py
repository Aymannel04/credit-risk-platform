"""Container tests that need no Docker: the recipe (Dockerfile, .dockerignore, service requirements) is checked as text,
and the smoke-test script is proven by running it against a live in-process server.
The real image is built and smoke-tested in CI (see .github/workflows/ci.yml)."""
import ast
import importlib.util
import posixpath
import re
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from service.main import create_app

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE = [ln.strip() for ln in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
HEAVY = {"numpy", "pandas", "scikit-learn", "scipy", "xgboost", "duckdb", "dagster", "shap", "matplotlib", "streamlit", "pyarrow", "joblib"}


def _instructions(name: str) -> list[str]:
    return [ln.strip()[len(name):].strip() for ln in DOCKERFILE.splitlines() if ln.strip().upper().startswith(name + " ")]


def _local_copies() -> list[tuple[list[str], str]]:
    """(sources, destination) of every COPY that comes from the build context (not from another image)."""
    out = []
    for args in _instructions("COPY"):
        if args.startswith("--from"):
            continue
        parts = args.split()
        out.append((parts[:-1], parts[-1]))
    return out


# ---------- the recipe ----------

def test_dockerignore_is_an_allowlist_that_excludes_data_and_secrets():
    assert IGNORE[0] == "*"
    allowed = {ln[1:] for ln in IGNORE if ln.startswith("!")}
    assert allowed == {"requirements-service.txt", "credit/__init__.py", "credit/serving/__init__.py", "credit/serving/model_file.py",
                       "service", "models/scorecard_v2.json"}
    for forbidden in ("data", "results", "tests", ".git", ".env", "docs", "config"):
        assert not any(a == forbidden or a.startswith(forbidden + "/") for a in allowed), forbidden


def test_dockerfile_pins_the_base_image_and_the_adapter():
    base = re.search(r"^FROM\s+(\S+)", DOCKERFILE, re.M).group(1)
    assert ":" in base and not base.endswith(":latest"), base
    assert re.search(r"aws-lambda-adapter:\d+\.\d+\.\d+@sha256:[0-9a-f]{64} ", DOCKERFILE), "the Lambda adapter must be pinned to an exact version AND its content fingerprint"


def test_dockerfile_never_copies_the_whole_context_and_never_runs_as_root():
    for sources, _ in _local_copies():
        assert "." not in sources and "./" not in sources and "*" not in sources, sources
    assert not _instructions("ADD")
    user = _instructions("USER")[-1]
    assert user not in ("root", "0")
    assert "curl" not in DOCKERFILE.lower() and "| sh" not in DOCKERFILE


def test_every_copied_source_exists_and_is_allowed_by_dockerignore():
    allowed = [ln[1:] for ln in IGNORE if ln.startswith("!")]
    for sources, _ in _local_copies():
        for s in sources:
            p = s.rstrip("/")
            assert (ROOT / p).exists(), f"COPY source missing: {s}"
            assert any(p == a or p.startswith(a + "/") for a in allowed), f"{s} is not allowed by .dockerignore"


def test_expected_image_file_list_matches_the_dockerfile():
    expected = set((ROOT / "scripts" / "expected_image_files.txt").read_text(encoding="utf-8").split())
    derived = set()
    for sources, dest in _local_copies():
        for s in sources:
            p = ROOT / s.rstrip("/")
            if p.is_dir():  # a directory is copied into dest, keeping its inner layout
                for f in p.rglob("*"):
                    if f.is_file() and "__pycache__" not in f.parts:
                        derived.add(posixpath.normpath(posixpath.join("/app", dest, f.relative_to(p).as_posix())))
            elif dest.endswith("/"):  # a file copied into a directory keeps its name
                derived.add(posixpath.normpath(posixpath.join("/app", dest, p.name)))
            else:  # a file copied to an exact path
                derived.add(posixpath.normpath(posixpath.join("/app", dest)))
    assert derived == expected, (sorted(derived ^ expected))


# ---------- the libraries ----------

def _pins(path: Path) -> dict[str, str]:
    out = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#"):
            name, _, version = ln.partition("==")
            assert version, f"not pinned: {ln}"
            out[name.strip().lower().replace("_", "-")] = version.strip()
    return out


def test_service_requirements_are_light_and_in_sync_with_the_project():
    service, project = _pins(ROOT / "requirements-service.txt"), _pins(ROOT / "requirements.txt")
    assert not HEAVY & set(service)
    for top in ("fastapi", "pydantic", "starlette", "uvicorn"):
        assert service[top] == project[top], top


def test_the_api_code_imports_only_what_the_container_has():
    allowed = set(sys.stdlib_module_names) | {"fastapi", "pydantic", "starlette", "uvicorn", "credit", "service"}
    files = [*sorted((ROOT / "service").glob("*.py")), ROOT / "credit" / "serving" / "model_file.py"]
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for n in names:
                assert n.split(".")[0] in allowed, f"{f.name} imports {n}, which is not in the container"
    own = {n.module for f in files for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
           if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in ("credit", "service")}
    assert own <= {"credit.serving.model_file", "service.schemas"}, own  # nothing else of the repo is needed


# ---------- the smoke-test script, proven against a live server ----------

def _load_smoke():
    spec = importlib.util.spec_from_file_location("smoke_test_api", ROOT / "scripts" / "smoke_test_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def live_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "the test server did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_smoke_script_passes_against_the_real_app(live_url):
    smoke = _load_smoke()
    assert smoke.wait_until_alive(live_url, 5)
    assert smoke.run_checks(live_url) == []


def test_smoke_script_fails_when_the_model_id_is_wrong(live_url):
    smoke = _load_smoke()
    fails = smoke.run_checks(live_url, expect_model_id="000000000000")
    assert any("model id" in f for f in fails)


def test_smoke_script_reports_a_dead_service():
    smoke = _load_smoke()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert smoke.wait_until_alive(f"http://127.0.0.1:{port}", 1) is False


# ---------- signed requests (for the locked Lambda Function URL) ----------

def _fake_credentials():
    from botocore.credentials import Credentials

    # AWS's own documentation example values, assembled at run time: they are not real and open nothing
    return Credentials("AKIA" + "IOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPx" + "RfiCYEXAMPLEKEY", token="example-session-token")


def test_signer_adds_a_sigv4_authorization_for_the_lambda_service():
    smoke = _load_smoke()
    sign = smoke.make_signer(_fake_credentials(), "eu-north-1")
    headers = sign("POST", "https://abc123.lambda-url.eu-north-1.on.aws/score", b'{"a": 1}', {"content-type": "application/json"})
    lowered = {k.lower(): v for k, v in headers.items()}
    auth = lowered["authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIA")
    assert "/eu-north-1/lambda/aws4_request" in auth, "the signing scope must name the region and the service 'lambda'"
    assert "SignedHeaders=" in auth and "host" in auth.split("SignedHeaders=")[1].split(",")[0]
    assert "x-amz-date" in lowered and lowered["x-amz-security-token"] == "example-session-token"
    assert lowered["content-type"] == "application/json"


def test_signature_depends_on_the_body_and_the_credentials():
    smoke = _load_smoke()
    sign = smoke.make_signer(_fake_credentials(), "eu-north-1")
    url = "https://abc123.lambda-url.eu-north-1.on.aws/score"
    one = {k.lower(): v for k, v in sign("POST", url, b"one", {}).items()}
    two = {k.lower(): v for k, v in sign("POST", url, b"two", {}).items()}
    assert one["authorization"].split("Signature=")[1] != two["authorization"].split("Signature=")[1]


def test_call_sends_the_signed_headers_and_stays_unsigned_by_default():
    import http.server

    seen = []

    class Capture(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append({k.lower(): v for k, v in self.headers.items()})
            body = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        smoke = _load_smoke()
        assert smoke.call(base, "GET", "/health")[0] == 200
        assert "authorization" not in seen[-1], "no signing unless asked"
        smoke.SIGNER = smoke.make_signer(_fake_credentials(), "eu-north-1")
        assert smoke.call(base, "GET", "/health")[0] == 200
        assert seen[-1]["authorization"].startswith("AWS4-HMAC-SHA256")
    finally:
        server.shutdown()
        thread.join(timeout=5)


# ---------- network trouble must not crash the smoke test ----------

class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body, self.status = body, status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_slow_handshake_is_retried_and_then_succeeds(monkeypatch):
    import urllib.error

    smoke = _load_smoke()
    monkeypatch.setattr(smoke.time, "sleep", lambda s: None)
    calls = []

    def flaky(req, timeout=None):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.URLError(TimeoutError("_ssl.c:1011: The handshake operation timed out"))
        return _FakeResponse(b'{"status": "ok"}')

    monkeypatch.setattr(smoke.urllib.request, "urlopen", flaky)
    assert smoke.call("https://example.test", "GET", "/health") == (200, {"status": "ok"})
    assert len(calls) == 3


def test_persistent_network_trouble_becomes_a_failed_check_not_a_traceback(monkeypatch):
    import urllib.error

    smoke = _load_smoke()
    monkeypatch.setattr(smoke.time, "sleep", lambda s: None)

    def always_down(req, timeout=None):
        raise urllib.error.URLError(TimeoutError("handshake timed out"))

    monkeypatch.setattr(smoke.urllib.request, "urlopen", always_down)
    status, text = smoke.call("https://example.test", "GET", "/health")
    assert status == 0 and "network error after 3 attempts" in text
    fails = smoke.run_checks("https://example.test", expect_model_id="x")
    assert fails and any("got 0" in f or "answered 0" in f for f in fails)  # reported, not raised


def test_a_real_error_answer_is_never_retried(monkeypatch):
    import io
    import urllib.error

    smoke = _load_smoke()
    monkeypatch.setattr(smoke.time, "sleep", lambda s: pytest.fail("a real HTTP answer must not be retried"))
    seen = []

    def forbidden(req, timeout=None):
        seen.append(1)
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message": "Forbidden"}'))

    monkeypatch.setattr(smoke.urllib.request, "urlopen", forbidden)
    assert smoke.call("https://example.test", "GET", "/health") == (403, {"message": "Forbidden"})
    assert len(seen) == 1


def test_every_retry_is_signed_again(monkeypatch):
    import urllib.error

    smoke = _load_smoke()
    monkeypatch.setattr(smoke.time, "sleep", lambda s: None)
    signed = []
    monkeypatch.setattr(smoke, "SIGNER", lambda method, url, body, headers: signed.append(1) or dict(headers))

    def down(req, timeout=None):
        raise urllib.error.URLError(TimeoutError("x"))

    monkeypatch.setattr(smoke.urllib.request, "urlopen", down)
    smoke.call("https://example.test", "GET", "/health", attempts=3)
    assert len(signed) == 3
