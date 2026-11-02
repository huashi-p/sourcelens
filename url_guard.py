import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


class SourceReadError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def is_public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


async def validate_public_url(url):
    parsed = urlsplit(str(url).strip())

    if parsed.scheme not in {"http", "https"}:
        raise SourceReadError("invalid_scheme", "只允许 HTTP 和 HTTPS")

    if parsed.username or parsed.password:
        raise SourceReadError("invalid_url", "URL 不能包含账号密码")

    if not parsed.hostname:
        raise SourceReadError("invalid_url", "URL 缺少主机名")

    try:
        port = parsed.port
    except ValueError as e:
        raise SourceReadError("invalid_url", "URL 端口格式错误") from e

    if port not in {None, 80, 443}:
        raise SourceReadError("blocked_port", "只允许 80 或 443")

    hostname = parsed.hostname.rstrip(".").lower()

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not literal_ip.is_global:
            raise SourceReadError("blocked_address", "不能访问内网地址")
    else:
        loop = asyncio.get_running_loop()

        try:
            addresses = await loop.getaddrinfo(
                hostname,
                None,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as e:
            raise SourceReadError("dns_error", "域名解析失败") from e

        resolved = {entry[4][0] for entry in addresses}

        if not resolved:
            raise SourceReadError("dns_error", "域名没有可用地址")

        if any(not is_public_ip(address) for address in resolved):
            raise SourceReadError(
                "blocked_address",
                "域名解析到了非公网地址",
            )

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )
