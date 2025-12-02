"""Theme model - taxonomy for classifying datasets."""

from typing import Optional
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ArrayOfText


class Theme(Base):
    """
    Taxonomy for classifying datasets.

    Provides a hierarchical classification system for datasets.
    """

    __tablename__ = "themes"

    # Primary key is the theme code
    code: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Human-readable name
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Keywords for auto-classification
    aliases: Mapped[Optional[list[str]]] = mapped_column(ArrayOfText(), nullable=True)
    # Example: hydro theme has aliases ["water", "stream", "river", "watershed"]

    # Hierarchical structure
    parent_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("themes.code", ondelete="SET NULL"),
        nullable=True,
    )

    # Icon or color for UI
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<Theme(code='{self.code}', name='{self.name}')>"
