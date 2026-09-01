"""
profile_tools.py — Lab 2: Tools for fetching student data.

All data access is delegated to PlacementConnector; tools do NOT open files.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import AccessContext, StudentProfile


def get_student_profile(
    student_id: str,
    connector: PlacementConnector,
) -> StudentProfile:
    """
    Retrieve a student profile through the connector.

    Args:
        student_id: The unique identifier for the student.
        connector:  An initialised PlacementConnector instance.

    Returns:
        A validated StudentProfile Pydantic model.

    Raises:
        KeyError: If no student with the given ID exists.
        UnauthorizedAccessError: If the caller's AccessContext forbids access.
    """
    return connector.get_student_profile(student_id)


def get_resume(
    student_id: str,
    connector: PlacementConnector,
) -> dict:
    """Return a compact resume summary for the given student."""
    return connector.get_resume(student_id)
