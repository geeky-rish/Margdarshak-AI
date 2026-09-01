"""
role_tools.py — Lab 2: Tools for fetching role requirement data.

All data access is delegated to PlacementConnector.
"""

from __future__ import annotations

from app.connector.placement_connector import PlacementConnector
from app.models.schemas import RoleRequirements


def get_role_requirements(
    role_name: str,
    connector: PlacementConnector,
) -> RoleRequirements:
    """
    Retrieve role requirements through the connector.

    Args:
        role_name:  The name of the target role (case-insensitive).
        connector:  An initialised PlacementConnector instance.

    Returns:
        A validated RoleRequirements Pydantic model.

    Raises:
        KeyError: If the role is not found.
    """
    return connector.get_role_requirements(role_name)


def list_available_roles(connector: PlacementConnector) -> list[str]:
    """Return the names of all roles currently supported by the system."""
    return connector.list_all_roles()
