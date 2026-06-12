import logging
from sealman.db.repos.device import DeviceRepository
from sealman.exceptions import IoTBackendAPIError

from sealman.routers.general.schemas import DeviceMetadataResponse

logger = logging.getLogger("EdgeConfigAPI")

async def get_device_metadata(device: str, repo: DeviceRepository):
    result = await repo.get_device_metadata(device_id=device)
    if result is None:
        raise IoTBackendAPIError(
            f"Could not find device {device} from database to update",
            404
        )
    return DeviceMetadataResponse(
        deviceId=result["device_id"],
        deviceMetadata=result["device_metadata"],
        createdAt=result["created_at"],
        updatedAt=result["updated_at"]
    )