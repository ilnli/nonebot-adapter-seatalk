from nonebot.exception import ActionFailed as BaseActionFailed
from nonebot.exception import AdapterException
from nonebot.exception import ApiNotAvailable as BaseApiNotAvailable
from nonebot.exception import NetworkError as BaseNetworkError


class SeaTalkAdapterException(AdapterException):
    def __init__(self, message: str = "") -> None:
        super().__init__("SeaTalk", message)


class NetworkError(SeaTalkAdapterException, BaseNetworkError):
    pass


class ActionFailed(SeaTalkAdapterException, BaseActionFailed):
    def __init__(
        self,
        code: int | str,
        message: str,
        *,
        api: str,
        request_id: str | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(f"{api} failed (code={code})")
        self.code = code
        self.message = message
        self.api = api
        self.request_id = request_id
        self.retry_after = retry_after


class ApiNotAvailable(SeaTalkAdapterException, BaseApiNotAvailable):
    pass


class UnsupportedMessage(SeaTalkAdapterException):
    pass


class InvalidEvent(SeaTalkAdapterException):
    pass


class EventCapacityExceeded(SeaTalkAdapterException):
    pass
