FROM luban-aiops/base-uv:al2023

# The sync engine shells out to git for type=git sources; keep git out of the
# shared base image and install it only where federation needs it.
USER root
RUN dnf install -y git && dnf clean all
USER app

WORKDIR /app

COPY --chown=app:app .python-version pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "skills-hub"]
