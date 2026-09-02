FROM luban-aiops/base-uv:al2023

WORKDIR /app

COPY --chown=app:app .python-version pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src

# Playwright installs as a library only (SPEC-049): browser binaries stay
# out of this image; the gateway connects over CDP to a sidecar browser.
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "tool-gateway"]
