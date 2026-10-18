"""How the agent gets the score: the ONLY tool of the agent, and it is read-only.

- OfflineScorer: the same API code as on AWS Lambda, run inside this process (no network, no AWS, no cost).
- LiveScorer: the real Lambda API behind its locked URL, with signed requests (SigV4) from your AWS login. It only POSTs a loan to /explain.
The URL is never printed or saved. The API never stores anything.
"""
import json
import time
import urllib.error
import urllib.request

REQUIRED = ("score", "probability_of_default", "reasons", "outside_training_range")


class ApiError(RuntimeError):
    pass


def check_answer(answer: object) -> dict:
    if not isinstance(answer, dict) or any(k not in answer for k in REQUIRED):
        raise ApiError("the scoring API answered something unexpected (missing " + ", ".join(
            k for k in REQUIRED if not isinstance(answer, dict) or k not in answer) + ")")
    if not isinstance(answer["probability_of_default"], (int, float)) or not 0 <= answer["probability_of_default"] <= 1:
        raise ApiError("the probability of default is not a number between 0 and 1")
    return answer


class OfflineScorer:
    """Context manager: `with OfflineScorer() as scorer: scorer.explain(loan)`."""

    name = "in-process API (same code as the Lambda)"

    def __enter__(self):
        from fastapi.testclient import TestClient

        from service.main import create_app

        self._client = TestClient(create_app())
        self._client.__enter__()
        return self

    def __exit__(self, *exc):
        return self._client.__exit__(*exc)

    def explain(self, loan: dict) -> dict:
        response = self._client.post("/explain", json=loan)
        if response.status_code != 200:
            raise ApiError(f"the API refused the loan (HTTP {response.status_code}); fields: " + _fields(response))
        return check_answer(response.json())


def _fields(response) -> str:
    try:
        return ", ".join(sorted({".".join(str(p) for p in e.get("loc", [])[1:]) for e in response.json().get("detail", [])})) or "unknown"
    except Exception:
        return "unknown"


class LiveScorer:
    name = "live AWS Lambda API (locked URL, signed requests)"

    def __init__(self, url: str, profile: str = "credit-admin", region: str = "eu-north-1", urlopen=urllib.request.urlopen,
                 sign=None, sleep=time.sleep, timeout: float = 20.0, attempts: int = 3):
        if not url.startswith("https://"):
            raise ApiError("the API address must start with https://")
        self._url, self._urlopen, self._sleep, self._timeout, self._attempts = url.rstrip("/"), urlopen, sleep, timeout, attempts
        self._sign = sign or self._make_signer(profile, region)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @staticmethod
    def _make_signer(profile: str, region: str):
        import botocore.session
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        credentials = botocore.session.Session(profile=profile).get_credentials()
        if credentials is None:
            raise ApiError(f"no AWS credentials for the profile '{profile}': run  aws sso login --profile {profile}")
        frozen = credentials.get_frozen_credentials()

        def sign(method: str, url: str, body: bytes, headers: dict) -> dict:
            request = AWSRequest(method=method, url=url, data=body, headers=dict(headers))
            SigV4Auth(frozen, "lambda", region).add_auth(request)
            return dict(request.headers)

        return sign

    def explain(self, loan: dict) -> dict:
        body = json.dumps(loan).encode("utf-8")
        for attempt in range(self._attempts):
            headers = self._sign("POST", f"{self._url}/explain", body, {"Content-Type": "application/json"})  # signed again on every try
            request = urllib.request.Request(f"{self._url}/explain", data=body, method="POST", headers=headers)
            try:
                with self._urlopen(request, timeout=self._timeout) as response:
                    return check_answer(json.loads(response.read().decode("utf-8")))
            except urllib.error.HTTPError as e:
                raise ApiError(f"the API answered HTTP {e.code}" + (" (login expired? run aws sso login)" if e.code == 403 else "")) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                if attempt + 1 < self._attempts:
                    self._sleep(2 * (attempt + 1))
                    continue
                raise ApiError("could not reach the API (network or timeout)") from None
            except json.JSONDecodeError:
                raise ApiError("the API did not answer valid JSON") from None
        raise ApiError("no answer from the API")
