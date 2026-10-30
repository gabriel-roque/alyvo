FROM mcr.microsoft.com/playwright:v1.56.1-noble

WORKDIR /workspace
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt ./api-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --break-system-packages torch --index-url https://download.pytorch.org/whl/cpu \
    && python3 -m pip install --break-system-packages -r api-requirements.txt \
       'pytest>=8.2,<9' 'pytest-asyncio>=0.23,<1' 'pytest-cov>=5,<8' \
       'ruff>=0.5,<1' 'ragas>=0.4,<0.5' 'openai>=1,<3' \
       'langchain-community>=0.3.27,<0.4' 'rapidfuzz>=3,<4'

COPY pyproject.toml ./
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
RUN python3 -m pip install --break-system-packages --no-deps -e .

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci

COPY . .
ENV PYTHONPATH=/workspace/apps/api:/workspace/apps/worker
CMD ["bash", "scripts/validate-container.sh"]
