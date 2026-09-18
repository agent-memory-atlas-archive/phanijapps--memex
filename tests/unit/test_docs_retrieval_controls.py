from pathlib import Path


def test_architecture_pins_retrieval_evaluation_security_controls() -> None:
    architecture = Path("docs/architecture/overview.md").read_text(encoding="utf-8")

    required_topics = (
        "Retrieval evaluation security controls",
        "offline Salesforce facts",
        "maintainer-supplied local Project Gutenberg catalog import",
        "fixture output is confined",
        "compressed and expanded parser limits",
        "no network",
        "fail closed",
        "retained reports are redacted",
    )

    for topic in required_topics:
        assert topic.casefold() in architecture.casefold()
