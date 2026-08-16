"""Baseline for the existing ECloe Pay and Market SQL schemas."""

from collections.abc import Sequence

revision: str = "20260728_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # schema.sql remains the bootstrap path for an empty database.
    # Existing installations can be stamped at this revision before upgrading.
    pass


def downgrade() -> None:
    pass
