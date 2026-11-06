FROM mcr.microsoft.com/playwright:v1.56.1-noble

COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/

WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/.venv/bin:$PATH" \
    PYTHONPATH=/workspace/apps/api:/workspace/apps/worker

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --no-install-project

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/docs/package.json apps/docs/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --extra dev
CMD ["bash", "scripts/validate-container.sh"]
