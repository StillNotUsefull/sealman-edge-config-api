# Public auth API for sealman
from sealman._internal.authorization.permission_check import (
    PermissionCheck,
    PathParamPermissionCheck,
    QueryParamPermissionCheck,
    EntityLookup,
)
from sealman._internal.authorization.permission_types import Device, Platform
from sealman._internal.authorization.resource_types import DEVICE, PLATFORM

__all__ = [
    # Permission check FastAPI dependencies
    "PermissionCheck",
    "PathParamPermissionCheck",
    "QueryParamPermissionCheck",
    "EntityLookup",
    # Permission constants
    "Device",
    "Platform",
    # Resource type constants
    "DEVICE",
    "PLATFORM",
]
