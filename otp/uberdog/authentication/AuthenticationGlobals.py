from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Mapping, Callable, Optional

import requests
from requests import Response

# Authentication scheme modes to be communicated between UD and client.
AUTHENTICATION_SCHEME_DEVTOKEN = 1
AUTHENTICATION_SCHEME_DISCORD = 2


@dataclass
class DiscordUserInformation:
    """
    Wrapper that contains basic information about a Discord user.
    """
    userId: int
    username: str
    pfp: str

@dataclass
class DiscordAuthenticationEventContext:
    """
    Event context that is passed along when a user authenticates via Discord.
    """
    code: str
    session: str

    AUTH_EVENT_IDENTIFIER = "discord-authentication-event"


# Thread pool for outgoing HTTP requests. Since we can't really utilize asyncio technology to its fullest,
# this is probably the next best thing. This can probably be in its own utilities class later, but we only really use
# it for OAuth2 authentication with Discord currently.
EXECUTOR_POOL = ThreadPoolExecutor(max_workers=5)

def send_get(
        endpoint: str,
        data: Mapping[str, str | bytes | None] | None = None,
        headers: Mapping[str, str | bytes | None] | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30,
        callback: Optional[Callable[[Optional[Response]], None]]  = None) -> None:
    """
    Sends a post request without blocking the main thread. Pass in a callback to execute code when it resolves.
    If the request times out, the callback will still be executed, but None will be passed as a parameter.
    If the request succeeds in any way, the request object will be passed in as a parameter.
    """
    __do_req(requests.get, endpoint, data, headers, auth, timeout, callback)

def send_post(
        endpoint: str,
        data: Mapping[str, str | bytes | None] | None = None,
        headers: Mapping[str, str | bytes | None] | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30,
        callback: Optional[Callable[[Optional[Response]], None]]  = None) -> None:
    """
    Sends a post request without blocking the main thread. Pass in a callback to execute code when it resolves.
    If the request times out, the callback will still be executed, but None will be passed as a parameter.
    If the request succeeds in any way, the request object will be passed in as a parameter.
    """
    __do_req(requests.post, endpoint, data, headers, auth, timeout, callback)

def __do_req(
        method: Callable,
        endpoint: str,
        data: Mapping[str, str | bytes | None] | None = None,
        headers: Mapping[str, str | bytes | None] | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30,
        callback: Optional[Callable[[Optional[Response]], None]] = None):
    """
    Performs a web request of the given method. This method is purely here to reduce code duplication.
    """
    def run():
        try:
            response = method(
                endpoint,
                data=data,
                headers=headers,
                auth=auth,
                timeout=timeout
            )
        except requests.exceptions.Timeout:
            callback(None)
            return

        callback(response)

    EXECUTOR_POOL.submit(run)
