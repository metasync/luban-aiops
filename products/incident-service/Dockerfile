FROM luban-aiops/base-uv:al2023

WORKDIR /app

COPY --chown=app:app .python-version pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "incident-service"]
