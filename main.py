from sealman.db import DeviceRepository, get_repository
from sealman.sems import SmartEMS, get_sems
from fastapi import APIRouter, Depends
from sealman import App

template_router = APIRouter(prefix="/templates", tags=["Templates"])


@template_router.get("/")
async def get_templates(
    sems: SmartEMS = Depends(get_sems),
    devices: DeviceRepository = Depends(get_repository(DeviceRepository)),
):
    return ["tempalte-1", "template-2"]


app = App(routers=[template_router])
