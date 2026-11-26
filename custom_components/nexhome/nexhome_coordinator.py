import asyncio
import logging
from datetime import timedelta
import async_timeout

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, TIME_NUMBER

_LOGGER = logging.getLogger(__name__)

class NexhomeCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device"""

    def __init__(self, hass, tool, params, update_interval=None):
        """Initialize the data update coordinator.
        
        Args:
            hass: Home Assistant instance
            tool: ServiceTool instance
            params: Parameters for device property query
            update_interval: Update interval in seconds (default: TIME_NUMBER from const)
        """
        if update_interval is None:
            update_interval = TIME_NUMBER
        DataUpdateCoordinator.__init__(
            self,
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self._tool = tool
        self._params = params
        self._results = {}
        # 失败退避：基础间隔 + 连续失败计数，网关卡顿时自动拉长轮询，恢复后自动回落
        self._base_interval = update_interval
        self._fail_count = 0

    async def _async_update_data(self):
        try:
            device_property = await self._tool.getProperties(self.hass, self._params)
        except Exception as err:
            device_property = False

        if device_property:
            # 成功：重置失败计数并恢复基础轮询间隔
            if self._fail_count:
                self._fail_count = 0
                self.update_interval = timedelta(seconds=self._base_interval)
                _LOGGER.debug("网关恢复，轮询间隔恢复为 %ss", self._base_interval)
            return device_property

        # 失败/无响应：按连续失败次数阶梯退避，避免线程堆积重试压垮网关
        self._fail_count += 1
        if self._fail_count == 1:
            backoff = self._base_interval * 2
        elif self._fail_count == 2:
            backoff = self._base_interval * 4
        else:
            backoff = min(self._base_interval * 8, 120)
        if int(self.update_interval.total_seconds()) != backoff:
            self.update_interval = timedelta(seconds=backoff)
            _LOGGER.warning("网关连续失败 %s 次，轮询间隔临时提高到 %ss", self._fail_count, backoff)
        return False
