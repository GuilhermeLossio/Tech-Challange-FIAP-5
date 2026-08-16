from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "recommendation-system.md"
DIAGRAMS = {
    "recommendation-system-overview.svg",
    "recommendation-decision-flow.svg",
    "recommendation-training-lifecycle.svg",
    "recommendation-privacy-boundary.svg",
    "choice-model-generation-pipeline.svg",
    "choice-model-selection-flow.svg",
    "choice-model-policy-comparison.svg",
}
CHOICE_DOC = ROOT / "docs" / "choice-model-generation.md"


def test_recommendation_document_covers_required_operating_topics() -> None:
    content = DOC.read_text(encoding="utf-8")
    required = {
        "## Architecture",
        "## Public API v2",
        "## Feature Catalog",
        "## Privacy and LGPD Controls",
        "## Algorithms",
        "## Cold Start",
        "## Feedback and Reward Attribution",
        "## Persistence",
        "## Deterministic Synthetic Seed",
        "## Training Lifecycle",
        "## Evaluation",
        "## Promotion and Rollback",
        "## Azure Population Preflight",
        "## Monitoring and Alerts",
        "## Limitations",
    }
    assert required <= set(line.strip() for line in content.splitlines())
    for algorithm in (
        "Deterministic baseline",
        "Content affinity",
        "Likelihood ranker",
        "Epsilon-Greedy",
        "UCB1",
        "Thompson Sampling",
    ):
        assert f"### {algorithm}" in content
    for status in ("Implemented", "Planned for demo", "Future", "Out of scope"):
        assert status in content


def test_choice_model_generation_document_covers_each_policy() -> None:
    content = CHOICE_DOC.read_text(encoding="utf-8")
    required = {
        "## Generation Pipeline",
        "## Runtime Selection",
        "## Policy Comparison",
        "## Model Details",
        "## Selection and Constraints",
    }
    assert required <= set(line.strip() for line in content.splitlines())
    for policy in (
        "Deterministic Baseline",
        "Content Affinity",
        "Likelihood Ranker",
        "Epsilon-Greedy",
        "UCB1",
        "Thompson Sampling",
    ):
        assert policy in content
    for diagram in (
        "choice-model-generation-pipeline.svg",
        "choice-model-selection-flow.svg",
        "choice-model-policy-comparison.svg",
    ):
        assert diagram in content


def test_recommendation_diagrams_are_linked_from_primary_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "Architecture.md").read_text(encoding="utf-8")
    for diagram in DIAGRAMS:
        assert (ROOT / "docs" / diagram).exists()
        assert diagram in readme
        assert diagram in architecture


def test_feature_manifest_contains_no_blocked_attributes() -> None:
    manifest = json.loads(
        (ROOT / "src" / "recommendation" / "feature_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(manifest).casefold()
    for blocked in ("sex", "gender", "mens", "womens", "email", "balance", "credit_score"):
        assert f'"{blocked}"' not in serialized


def test_hillstrom_gender_coded_identifiers_are_isolated_to_offline_adapter() -> None:
    matches = []
    for base in (ROOT / "src", ROOT / "scripts"):
        for path in base.rglob("*.py"):
            content = path.read_text(encoding="utf-8").casefold()
            if "mens_email" in content or "womens_email" in content:
                matches.append(path.relative_to(ROOT).as_posix())

    assert sorted(matches) == ["src/data/legacy_hillstrom.py"]


def test_recommendation_sql_schema_is_idempotent_and_pseudonymous() -> None:
    schema = (ROOT / "src" / "recommendation" / "schema.sql").read_text(encoding="utf-8")
    assert "IF OBJECT_ID" in schema
    assert "IF NOT EXISTS" in schema
    assert "ecloe_features.feature_snapshots" in schema
    assert "ecloe_features.synthetic_interactions" in schema
    assert "subject_key" in schema
    assert "synthetic_seed" in schema
    assert "gender" not in schema.casefold()
    assert " sex " not in schema.casefold()
