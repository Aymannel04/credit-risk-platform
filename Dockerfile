# Scoring API container (portfolio project, not a lending product).
# The same image runs on a laptop, on any container host, and on AWS Lambda (through the Lambda Web Adapter below).
# Build:  docker build -t scoring-api:local .      Run:  docker run --rm -p 8080:8080 scoring-api:local
FROM python:3.13-slim-bookworm

# Lets this ordinary web app run inside AWS Lambda with no code change. v1.1.0 is the latest release (checked 2026-10-12).
# Outside Lambda it does nothing.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health

WORKDIR /app

# Only the libraries the API needs (no pandas, no scikit-learn): small image, fast start.
COPY requirements-service.txt ./
RUN pip install -r requirements-service.txt

# Only the files the API needs. No data, no training code, no tests (see .dockerignore, an allow-list).
COPY credit/__init__.py credit/__init__.py
COPY credit/serving/__init__.py credit/serving/model_file.py credit/serving/
COPY service/ service/
COPY models/scorecard_v2.json models/scorecard_v2.json

# Do not run as root.
RUN useradd --uid 10001 --no-create-home apiuser
USER 10001

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
