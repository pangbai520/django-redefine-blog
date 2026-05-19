import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit


class RemoteFetchError(ValueError):
    pass


@dataclass(frozen=True)
class RemoteData:
    body: bytes
    content_type: str
    url: str


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, *, timeout):
        super().__init__(
            host,
            port=443,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._ip = ip

    def connect(self):
        sock = socket.create_connection(
            (self._ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _resolve_ips(host):
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RemoteFetchError("The remote host could not be resolved.") from exc

    addresses = {row[4][0].split("%", 1)[0] for row in rows}
    if not addresses:
        raise RemoteFetchError("The remote host has no usable address.")
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise RemoteFetchError("Private or reserved remote addresses are not allowed.")
    return sorted(addresses)


def _check_url(url):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise RemoteFetchError("The remote URL is invalid.") from exc

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise RemoteFetchError("Remote resources must use HTTPS.")
    if parsed.username or parsed.password:
        raise RemoteFetchError("Credentials are not allowed in remote URLs.")
    if port not in (None, 443):
        raise RemoteFetchError("Remote resources must use the standard HTTPS port.")

    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
    return parsed, host, _resolve_ips(host)[0]


def _get_once(url, *, timeout, max_bytes):
    parsed, host, ip = _check_url(url)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query

    conn = _PinnedHTTPS(host, ip, timeout=timeout)
    try:
        conn.request(
            "GET",
            target,
            headers={
                "Accept": "application/json, text/html;q=0.9, text/plain;q=0.8",
                "User-Agent": "DjangoRedefine/1.0",
            },
        )
        response = conn.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            return None, response.getheader("Location", "")
        if not 200 <= response.status < 300:
            raise RemoteFetchError(
                f"The remote server returned HTTP {response.status}."
            )

        length = response.getheader("Content-Length")
        if length:
            try:
                if int(length) > max_bytes:
                    raise RemoteFetchError("The remote response is too large.")
            except ValueError:
                pass
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RemoteFetchError("The remote response is too large.")
        content_type = response.getheader("Content-Type", "").split(";", 1)[0]
        return RemoteData(body, content_type.lower().strip(), url), ""
    finally:
        conn.close()


def fetch_https(url, *, timeout=4, max_bytes=512 * 1024, redirects=3):
    """Fetch a small HTTPS resource without allowing access to local networks."""
    current = url
    for _ in range(redirects + 1):
        try:
            data, location = _get_once(
                current,
                timeout=timeout,
                max_bytes=max_bytes,
            )
        except RemoteFetchError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise RemoteFetchError("The remote request failed.") from exc
        if data is not None:
            return data
        if not location:
            raise RemoteFetchError("The remote redirect has no destination.")
        current = urljoin(current, location)
    raise RemoteFetchError("The remote server redirected too many times.")
