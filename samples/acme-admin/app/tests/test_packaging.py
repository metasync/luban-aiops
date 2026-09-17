"""SPEC-059 R-4: stand-alone packaging, asserted mechanically.

The app is deliberately *not* part of `make build`'s product loops, and its
version is deliberately *not* part of the platform's version lockstep. Both are
easy to get wrong later and invisible when they are, so both are asserted here
rather than left as a convention somebody has to remember.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from acme_admin import __version__

APP_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DIR = APP_DIR.parent
SAMPLES_DIR = SAMPLE_DIR.parent
REPO_ROOT = SAMPLES_DIR.parent

# The base image every product builds on, and the toolchain it pins.
BASE_IMAGE = "luban-aiops/base-uv:al2023"

# Skill directories `samples/deploy-samples.sh` already ships. The four this
# slice adds are asserted alongside them in test_skill_discovery below.
SHIPPED_SKILL_DIRS = {
    "web-checks/adhoc-password-reset",
    "web-checks/password-reset",
}


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _pyproject() -> dict:
    with open(APP_DIR / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)


def _skill_dirs() -> set[str]:
    """The same discovery `deploy-samples.sh` runs, rooted at `samples/`."""
    return {
        str(path.parent.relative_to(SAMPLES_DIR))
        for path in SAMPLES_DIR.rglob("skill")
        if path.is_dir()
    }


def _skill_id(sample_dir: str, filename: str) -> str:
    """Replicate the ConfigMap key + slug rule end to end.

    `deploy-samples.sh` mounts each document as `<sample-leaf>-<filename>`;
    `skills_hub.services.ingestion.slug_from_path` then lowercases it, drops the
    `.md`, and collapses every run of non-alphanumerics to a single `-`. The
    category directory is **not** part of the id — which is exactly why this
    slice's password-reset document is `ResetAcmePassword.md` and not
    `ResetUserPassword.md`: the latter would collide byte-identically with the
    shipped sample's id.
    """
    leaf = Path(sample_dir).name
    key = f"{leaf}-{filename}"
    stem = key[:-3] if key.lower().endswith(".md") else key
    return "samples/" + re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


# --- the image --------------------------------------------------------------


def test_the_dockerfile_mirrors_the_product_pattern() -> None:
    text = _read(APP_DIR / "Dockerfile")
    assert f"FROM {BASE_IMAGE}" in text
    # The lock and the source, owned by the runtime user, in the cached order.
    assert "COPY --chown=app:app .python-version pyproject.toml uv.lock README.md ./" in text
    assert "COPY --chown=app:app src ./src" in text
    assert "RUN uv sync --frozen --no-dev" in text
    assert "EXPOSE 8080" in text
    assert 'CMD ["uv", "run", "acme-admin"]' in text


def test_the_dockerfile_has_no_user_line() -> None:
    """`base-uv` already ends as `app` (uid 1000); a second USER would be noise."""
    text = _read(APP_DIR / "Dockerfile")
    assert not re.search(r"^USER\s", text, re.MULTILINE)


def test_the_dockerfile_copies_no_test_tree() -> None:
    """`--no-dev` excludes pytest; shipping the tests would be dead weight."""
    assert "tests" not in _read(APP_DIR / "Dockerfile")


# --- the Makefile -----------------------------------------------------------


def test_the_makefile_only_includes_the_shared_fragments() -> None:
    text = _read(APP_DIR / "Makefile")
    assert "IMAGE_NAME := acme-admin" in text
    assert "include ../../../mk/image.mk" in text
    assert "include ../../../mk/python.mk" in text
    # No build logic of its own: the fragments are the convention.
    assert "docker build" not in text


def test_the_app_is_not_in_the_platform_build_loops() -> None:
    root = _read(REPO_ROOT / "Makefile")
    for variable in ("IMAGE_PRODUCTS", "PYTHON_PRODUCTS"):
        match = re.search(rf"^{variable}\s*:=\s*(.*)$", root, re.MULTILINE)
        assert match, f"{variable} not found in the root Makefile"
        assert "acme-admin" not in match.group(1), (
            f"{variable} grew the tutorial image; `make build` must not carry it"
        )


# --- the toolchain ----------------------------------------------------------


def test_the_python_pin_matches_the_shared_base_image() -> None:
    pinned = _read(APP_DIR / ".python-version").strip()
    defaults = _read(REPO_ROOT / "mk" / "defaults.mk")
    match = re.search(r"^BASE_UV_PYTHON_VERSION\s*\?=\s*(\S+)", defaults, re.MULTILINE)
    assert match, "BASE_UV_PYTHON_VERSION not found in mk/defaults.mk"
    assert pinned == match.group(1)


def test_runtime_dependencies_are_the_shared_toolchain_only() -> None:
    project = _pyproject()["project"]
    assert project["requires-python"] == ">=3.12"
    assert project["dependencies"] == [
        "fastapi>=0.115,<1.0",
        "pydantic>=2.8,<3.0",
        "uvicorn[standard]>=0.30,<1.0",
    ]


def test_there_is_no_template_engine_and_no_database_driver() -> None:
    """R-1's rejections, asserted so they stay rejected."""
    text = _read(APP_DIR / "pyproject.toml").lower()
    for forbidden in ("jinja", "psycopg", "sqlalchemy", "aiosqlite", "redis"):
        assert forbidden not in text


def test_dev_dependencies_carry_the_test_client() -> None:
    dev = _pyproject()["dependency-groups"]["dev"]
    assert any(dep.startswith("pytest") for dep in dev)
    # `fastapi.testclient` needs httpx; without it the suite cannot run at all.
    assert any(dep.startswith("httpx") for dep in dev)


def test_the_console_script_is_the_documented_entry_point() -> None:
    assert _pyproject()["project"]["scripts"] == {"acme-admin": "acme_admin.main:run"}


# --- the lockfile -----------------------------------------------------------


def test_a_lockfile_is_committed() -> None:
    assert (APP_DIR / "uv.lock").is_file(), (
        "uv.lock must be committed: the Dockerfile runs `uv sync --frozen`"
    )


def test_the_lockfile_pins_the_app_itself_as_editable() -> None:
    text = _read(APP_DIR / "uv.lock")
    pattern = (
        rf'name = "acme-admin"\nversion = "{re.escape(__version__)}"\n'
        r'source = \{ editable = "\." \}'
    )
    assert re.search(pattern, text), "the app's own editable pin is missing/stale"


def test_the_package_version_matches_the_module_version() -> None:
    assert _pyproject()["project"]["version"] == __version__


def test_the_app_is_outside_the_platform_version_lockstep() -> None:
    """`validate_version.py` scans `products/*/pyproject.toml` and nothing else.

    A sample that joined the lockstep would force a VERSION bump to touch a
    tutorial app — and a tutorial app that drifted silently would be worse. This
    asserts the boundary is real rather than assumed.
    """
    script = _read(REPO_ROOT / "shared/shared-contracts/scripts/validate_version.py")
    assert 'products_dir.glob("*/pyproject.toml")' in script
    assert "samples" not in script


# --- skill discovery hygiene ------------------------------------------------


def test_no_skill_directory_lives_under_the_app_deploy_or_tests() -> None:
    """`deploy-samples.sh` discovers by directory name; the app must not confuse it."""
    for directory in _skill_dirs():
        assert not directory.startswith("acme-admin/app/")
        assert not directory.startswith("acme-admin/deploy/")
        assert "/tests" not in directory


def test_skill_discovery_finds_the_shipped_samples() -> None:
    found = _skill_dirs()
    assert SHIPPED_SKILL_DIRS <= found, sorted(found)


def test_derived_skill_ids_are_unique() -> None:
    """The slug-collision guard, made mechanical.

    Every `skill/*.md` under `samples/` becomes `samples/<leaf>-<slug>`, with the
    category directory dropped, so two samples in different categories can collide
    on a name that looks distinct in the tree.
    """
    ids: dict[str, str] = {}
    for sample_dir in sorted(_skill_dirs()):
        skill_dir = SAMPLES_DIR / sample_dir / "skill"
        for document in sorted(skill_dir.glob("*.md")):
            skill_id = _skill_id(sample_dir, document.name)
            assert skill_id not in ids, (
                f"{skill_id} is produced by both {ids.get(skill_id)} and "
                f"{sample_dir}/skill/{document.name}"
            )
            ids[skill_id] = f"{sample_dir}/skill/{document.name}"
    assert ids, "no sample skills discovered at all"


def test_the_shipped_password_reset_id_is_unchanged() -> None:
    """The naming rule this slice works around, pinned so it cannot drift."""
    assert (
        _skill_id("web-checks/password-reset", "ResetUserPassword.md")
        == "samples/password-reset-resetuserpassword"
    )


@pytest.mark.parametrize(
    "sample_dir,filename",
    [
        ("web-checks/password-reset", "ResetUserPassword.md"),
        ("web-checks/adhoc-password-reset", "ResetPasswordAdHoc.md"),
    ],
)
def test_shipped_ids_keep_their_shape(sample_dir: str, filename: str) -> None:
    assert _skill_id(sample_dir, filename).startswith("samples/")
    assert filename[:-3].lower() in _skill_id(sample_dir, filename)
