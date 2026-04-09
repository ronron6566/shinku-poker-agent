from http import HTTPStatus

import httpx


def is_engine_busy_exception(exception: Exception) -> bool:
    return isinstance(exception, httpx.HTTPStatusError) and exception.response.status_code in (
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    )
