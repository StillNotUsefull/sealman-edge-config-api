# Public SEMS API for sealman
from sealman._internal.smart_ems import SmartEMS
from fastapi import HTTPException


def get_sems() -> SmartEMS:
    """FastAPI dependency that provides access to the SmartEMS API client.

    Raises HTTP 503 if the SEMS client has not yet completed initialization
    (e.g. token exchange on startup is still pending or failed).

    Usage::

        from sealman.sems import get_sems, SmartEMS
        from fastapi import Depends

        @router.get("/{device}/custom")
        async def my_route(device: str, sems: SmartEMS = Depends(get_sems)):
            device_info = await sems.get_device_by_serial(device)
            ...
    """
    if not SmartEMS.init_done():
        raise HTTPException(status_code=503, detail="SEMS API not yet available")
    return SmartEMS


__all__ = ["get_sems", "SmartEMS"]
