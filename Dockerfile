# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM ghcr.io/astral-sh/uv:0.9.18-python${PYTHON_VERSION}-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

# Install locked dependencies, then install the project from its built wheel.
RUN uv sync --frozen --no-dev --no-install-project \
    && uv build --wheel --out-dir /dist \
    && uv pip install --python /opt/venv/bin/python --no-deps /dist/*.whl


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

LABEL org.opencontainers.image.title="Jev Compiler" \
      org.opencontainers.image.description="Compile decision policies into verified TypeSafe Jev artifacts." \
      org.opencontainers.image.source="https://github.com/triggeredcode/jev-compiler" \
      org.opencontainers.image.licenses="MIT"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid "${APP_GID}" jev \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home \
        --shell /usr/sbin/nologin jev

COPY --from=builder /opt/venv /opt/venv

WORKDIR /workspace
COPY --chown=jev:jev examples ./examples
RUN mkdir -p .jevcompiler && chown jev:jev .jevcompiler

USER jev:jev

ENTRYPOINT ["jevcompiler"]
CMD ["--help"]
