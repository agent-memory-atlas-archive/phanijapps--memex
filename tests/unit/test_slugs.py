from memex.domain.slugs import derive_slug, sha1_slug, slugify, unique_slug


class TestSlugify:
    def test_basic_kebab(self) -> None:
        assert slugify("Ruff linter") == "ruff-linter"

    def test_punctuation_replaced(self) -> None:
        assert slugify("Python 3.12 & ruff: setup!") == "python-3-12-ruff-setup"

    def test_hyphen_runs_collapse_and_edges_trim(self) -> None:
        assert slugify("--Hello --   World--") == "hello-world"

    def test_truncated_to_64(self) -> None:
        slug = slugify("x" * 200)
        assert len(slug) == 64

    def test_empty_when_nothing_survives(self) -> None:
        assert slugify("!!! ... ???") == ""


class TestUniqueSlug:
    def test_unchanged_when_free(self) -> None:
        assert unique_slug("ruff", {"other"}) == "ruff"

    def test_suffixed_on_collision(self) -> None:
        assert unique_slug("ruff", {"ruff"}) == "ruff-2"

    def test_increments_until_free(self) -> None:
        assert unique_slug("ruff", {"ruff", "ruff-2", "ruff-3"}) == "ruff-4"


class TestDeriveSlug:
    def test_kebab_default(self) -> None:
        assert derive_slug("My Tool Config") == "my-tool-config"

    def test_sha1_algo(self) -> None:
        assert derive_slug("My Tool Config", algo="sha1") == sha1_slug("My Tool Config")
        assert len(sha1_slug("x")) == 12
