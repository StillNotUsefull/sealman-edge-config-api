from typing import Union
from sealman._internal.authorization.permission_check import PathParamPermissionCheck
from sealman._internal.authorization import resource_types as Resource
from sealman._internal.authorization.permission_types import Device
from fastapi import Depends

from sealman._internal.routers.base_api_router import BaseAPIRouter
from sealman._internal.routers.network_discovery.schemas import NetworkScan, NetworkDiscover
from sealman._internal.common_schemas import DirectMethod
from sealman._internal.routers.network_discovery.routes.post_network_discover2 import post_network_discover2 as _post_network_discover2
from sealman._internal.routers.network_discovery.routes.get_network_topology import get_network_topology as _get_network_topology


network_discovery = BaseAPIRouter()

@network_discovery.post("/{device}/network/discover", tags=["Network Discovery"],
                        response_model=DirectMethod[NetworkScan])
async def post_network_discover(device: str, network_discover: NetworkDiscover,
                                 auth_context = Depends(PathParamPermissionCheck(Device.DISCOVER_NETWORK, Resource.DEVICE, "device"))):
    return await _post_network_discover2(device, network_discover, auth_context)


@network_discovery.get("/{device}/network/topology", tags=["Network Discovery"],
                       response_model=Union[NetworkScan, None])
async def get_network_topology(device: str,
                                _ = Depends(PathParamPermissionCheck(Device.READ, Resource.DEVICE, "device"))):
    return await _get_network_topology(device)
