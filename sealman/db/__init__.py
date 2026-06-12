# Public database API for sealman
from sealman._internal.db.base import Base
from sealman._internal.db.session import get_db, get_repository
from sealman._internal.db.registry import register_repository
from sealman._internal.db.repos.device import DeviceRepository
from sealman._internal.db.repos.compose import ComposeRepository
from sealman._internal.db.repos.password_renewal_task import PasswordRenewalTaskRepository

__all__ = [
    # SQLAlchemy base — extend this for custom models picked up by Alembic
    "Base",
    # FastAPI dependencies
    "get_db",
    "get_repository",
    # Repository registration
    "register_repository",
    # Repository interfaces
    "DeviceRepository",
    "ComposeRepository",
    "PasswordRenewalTaskRepository",
]
