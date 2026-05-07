from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import ssl
import ipaddress
import json
import os
from pathlib import Path
import socket
import stat
from typing import Any
from urllib.parse import urljoin, urlparse

from config import SETTINGS


MAX_CURL_BYTES = 512_000
MAX_CURL_CONTENT_CHARS = 10_000
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 8
TEXT_CONTENT_TYPES = (
    'text/',
    'application/json',
    'application/xml',
    'application/xhtml+xml',
    'application/javascript',
    'application/x-javascript',
)
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class CurlFetchError(Exception):
    pass


class ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {'script', 'style', 'noscript', 'svg', 'canvas', 'nav', 'header', 'footer', 'aside'}:
            self.skip_depth += 1
        if tag == 'title':
            self.in_title = True
        if tag in {'p', 'br', 'div', 'section', 'article', 'main', 'li', 'h1', 'h2', 'h3', 'pre', 'tr'}:
            self.text_parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {'script', 'style', 'noscript', 'svg', 'canvas', 'nav', 'header', 'footer', 'aside'} and self.skip_depth:
            self.skip_depth -= 1
        if tag == 'title':
            self.in_title = False
        if tag in {'p', 'div', 'section', 'article', 'main', 'li', 'h1', 'h2', 'h3', 'pre', 'tr'}:
            self.text_parts.append('\n')

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        self.text_parts.append(data)


def normalize_domain(domain: str) -> str:
    value = domain.strip().lower().rstrip('.')
    if not value:
        raise ValueError('domain must be non-empty')
    try:
        value.encode('ascii')
    except UnicodeEncodeError as exc:
        raise ValueError('domain must be ascii') from exc
    return value


def whitelist_path() -> Path:
    path = SETTINGS.curl_whitelist_path.expanduser().resolve()
    sandbox_dir = SETTINGS.sandbox_dir.expanduser().resolve()
    try:
        path.relative_to(sandbox_dir)
    except ValueError:
        return path
    raise ValueError('curl whitelist path must not be inside the sandbox')


def require_private_owner(path: Path, *, kind: str) -> None:
    info = path.stat()
    current_uid = os.getuid()
    if info.st_uid != current_uid:
        raise ValueError(f'curl whitelist {kind} must be owned by the Wallace runtime user')
    if kind == 'directory':
        unsafe_bits = stat.S_IRWXG | stat.S_IRWXO
        expected_mode = 0o700
    else:
        unsafe_bits = stat.S_IRWXG | stat.S_IRWXO
        expected_mode = 0o600
    if info.st_mode & unsafe_bits:
        raise ValueError(f'curl whitelist {kind} must not be accessible by group or others; expected mode {expected_mode:o}')


def ensure_whitelist_storage(*, create: bool) -> Path:
    path = whitelist_path()
    parent = path.parent
    if create:
        parent.mkdir(parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
    if parent.exists():
        require_private_owner(parent, kind='directory')
    elif create:
        raise ValueError('curl whitelist directory could not be created')

    if path.exists():
        require_private_owner(path, kind='file')
    elif create:
        path.write_text('{"domains": []}\n', encoding='utf-8')
        os.chmod(path, 0o600)
        require_private_owner(path, kind='file')
    return path


def load_whitelist() -> set[str]:
    path = ensure_whitelist_storage(create=False)
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding='utf-8'))
    domains = payload.get('domains', [])
    if not isinstance(domains, list):
        raise ValueError('curl whitelist domains must be a list')
    return {normalize_domain(str(domain)) for domain in domains}


def save_whitelist(domains: set[str]) -> None:
    path = ensure_whitelist_storage(create=True)
    payload = {'domains': sorted(normalize_domain(domain) for domain in domains)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.chmod(path, 0o600)


def add_domain_to_whitelist(domain: str) -> dict[str, Any]:
    try:
        normalized = normalize_domain(domain)
        domains = load_whitelist()
        domains.add(normalized)
        save_whitelist(domains)
        return {'status': 'ok', 'domain': normalized}
    except Exception as exc:
        return {'status': 'error', 'domain': domain, 'error': str(exc)}


def approval_id_for(domain: str, url: str) -> str:
    digest = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
    return f'curl:{normalize_domain(domain)}:{digest}'


def is_private_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_network_target(hostname: str) -> list[str]:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError('IP literal URLs are not allowed')

    infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise ValueError('domain did not resolve')
    if any(is_private_address(address) for address in addresses):
        raise ValueError('domain resolves to a private or unsafe address')
    return sorted(addresses)


def validate_url(url: str, whitelist: set[str], resolved_hosts: dict[str, list[str]] | None = None) -> tuple[str, str, list[str]]:
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise ValueError('only https URLs are allowed')
    if not parsed.hostname:
        raise ValueError('URL must include a hostname')
    if parsed.username or parsed.password:
        raise ValueError('URL userinfo is not allowed')
    if parsed.fragment:
        raise ValueError('URL fragments are not allowed')
    if parsed.port not in (None, 443):
        raise ValueError('only the default https port is allowed')

    domain = normalize_domain(parsed.hostname)
    if domain not in whitelist:
        raise PermissionError(domain)

    if resolved_hosts is not None and domain in resolved_hosts:
        addresses = resolved_hosts[domain]
    else:
        addresses = validate_network_target(domain)
        if resolved_hosts is not None:
            resolved_hosts[domain] = addresses
    return domain, parsed.geturl(), addresses


def normalize_fetch_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == 'http':
        return parsed._replace(scheme='https').geturl()
    return url


def compact_lines(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = ' '.join(raw_line.split())
        if not line:
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def extract_text(data: bytes, content_type: str) -> tuple[str, str]:
    charset = 'utf-8'
    for part in content_type.split(';')[1:]:
        key, _, value = part.strip().partition('=')
        if key.lower() == 'charset' and value:
            charset = value.strip()
            break

    text = data.decode(charset, errors='replace')
    if 'html' not in content_type.lower():
        return '', compact_lines(text)

    parser = ReadableHTMLParser()
    parser.feed(text)
    title = compact_lines(' '.join(parser.title_parts))
    content = compact_lines('\n'.join(parser.text_parts))
    return title, content


def read_limited_response(response: Any) -> tuple[bytes, bool]:
    data = response.read(MAX_CURL_BYTES + 1)
    truncated = len(data) > MAX_CURL_BYTES
    if truncated:
        data = data[:MAX_CURL_BYTES]
    return data, truncated


def parse_headers(raw_headers: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in raw_headers.split('\r\n'):
        name, separator, value = line.partition(':')
        if separator:
            headers[name.strip().lower()] = value.strip()
    return headers


def request_target(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or '/'
    if parsed.query:
        path = f'{path}?{parsed.query}'
    return path


def recv_until_headers(sock: ssl.SSLSocket) -> tuple[bytes, bytes]:
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = sock.recv(8192)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_CURL_BYTES:
            raise CurlFetchError('response headers are too large')
    header_data, _, body = data.partition(b'\r\n\r\n')
    return header_data, body


def read_http_body(sock: ssl.SSLSocket, initial_body: bytes, headers: dict[str, str]) -> tuple[bytes, bool]:
    if headers.get('transfer-encoding', '').lower() == 'chunked':
        return read_chunked_body(sock, initial_body)

    max_bytes = MAX_CURL_BYTES + 1
    chunks = [initial_body[:max_bytes]]
    remaining = max_bytes - len(chunks[0])

    content_length = headers.get('content-length')
    if content_length and content_length.isdigit():
        remaining = min(remaining, int(content_length) - len(initial_body))

    while remaining > 0:
        chunk = sock.recv(min(8192, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)

    data = b''.join(chunks)
    truncated = len(data) > MAX_CURL_BYTES
    if truncated:
        data = data[:MAX_CURL_BYTES]
    return data, truncated


def read_chunked_body(sock: ssl.SSLSocket, initial_body: bytes) -> tuple[bytes, bool]:
    buffer = initial_body
    body = bytearray()
    truncated = False

    def ensure_buffer() -> None:
        nonlocal buffer
        while b'\r\n' not in buffer:
            chunk = sock.recv(8192)
            if not chunk:
                raise CurlFetchError('incomplete chunked response')
            buffer += chunk

    while True:
        ensure_buffer()
        size_line, _, buffer = buffer.partition(b'\r\n')
        size_text = size_line.split(b';', 1)[0].strip()
        try:
            size = int(size_text, 16)
        except ValueError as exc:
            raise CurlFetchError('invalid chunked response') from exc
        if size == 0:
            break

        while len(buffer) < size + 2:
            chunk = sock.recv(8192)
            if not chunk:
                raise CurlFetchError('incomplete chunked response')
            buffer += chunk

        body.extend(buffer[:size])
        buffer = buffer[size + 2:]
        if len(body) > MAX_CURL_BYTES:
            truncated = True
            body = body[:MAX_CURL_BYTES]
            break

    return bytes(body), truncated


def fetch_once(url: str, domain: str, addresses: list[str]) -> tuple[int, str, bytes, bool, str | None]:
    parsed = urlparse(url)
    port = parsed.port or 443
    request = (
        f'GET {request_target(url)} HTTP/1.1\r\n'
        f'Host: {domain}\r\n'
        'User-Agent: WallaceDocFetcher/1.0\r\n'
        'Accept: text/html,text/plain,application/json,application/xml,*/*;q=0.1\r\n'
        'Accept-Encoding: identity\r\n'
        'Connection: close\r\n'
        '\r\n'
    ).encode('ascii')

    last_error: Exception | None = None
    for address in addresses:
        try:
            with socket.create_connection((address, port), timeout=FETCH_TIMEOUT_SECONDS) as raw_sock:
                raw_sock.settimeout(FETCH_TIMEOUT_SECONDS)
                context = ssl.create_default_context()
                with context.wrap_socket(raw_sock, server_hostname=domain) as sock:
                    sock.sendall(request)
                    header_data, initial_body = recv_until_headers(sock)
                    header_text = header_data.decode('iso-8859-1', errors='replace')
                    status_line, _, raw_headers = header_text.partition('\r\n')
                    parts = status_line.split()
                    if len(parts) < 2 or not parts[1].isdigit():
                        raise CurlFetchError('invalid HTTP response')
                    status_code = int(parts[1])
                    headers = parse_headers(raw_headers)
                    content_type = headers.get('content-type', '')
                    if status_code in REDIRECT_STATUSES:
                        return status_code, content_type, b'', False, headers.get('location')
                    if not any(content_type.lower().startswith(prefix) for prefix in TEXT_CONTENT_TYPES):
                        raise CurlFetchError('response is not a supported text content type')
                    data, truncated = read_http_body(sock, initial_body, headers)
                    return status_code, content_type, data, truncated, url
        except Exception as exc:
            last_error = exc
            continue

    raise CurlFetchError(str(last_error or 'connection failed'))


def approval_payload(domain: str, url: str) -> dict[str, Any]:
    return {
        'status': 'approval_required',
        'url': url,
        'domain': domain,
        'approval_id': approval_id_for(domain, url),
    }


def success_payload(original_url: str, final_url: str, content_type: str, data: bytes, byte_truncated: bool) -> dict[str, Any]:
    title, content = extract_text(data, content_type)
    content_truncated = len(content) > MAX_CURL_CONTENT_CHARS
    if content_truncated:
        content = content[:MAX_CURL_CONTENT_CHARS].rstrip()
    return {
        'status': 'ok',
        'url': original_url,
        'final_url': final_url,
        'title': title,
        'content': content,
        'truncated': byte_truncated or content_truncated,
    }


def curl_url(url: str) -> dict[str, Any]:
    original_url = str(url).strip()
    try:
        whitelist = load_whitelist()
        current_url = normalize_fetch_url(original_url)
        resolved_hosts: dict[str, list[str]] = {}

        for _ in range(MAX_REDIRECTS + 1):
            try:
                domain, validated_url, addresses = validate_url(current_url, whitelist, resolved_hosts)
            except PermissionError as exc:
                return approval_payload(str(exc), current_url)

            status_code, content_type, data, byte_truncated, next_url = fetch_once(validated_url, domain, addresses)
            if status_code in REDIRECT_STATUSES:
                if not next_url:
                    return {'status': 'error', 'url': current_url, 'error': 'redirect response missing location'}
                current_url = urljoin(current_url, next_url)
                continue
            if status_code >= 400:
                return {'status': 'error', 'url': current_url, 'error': f'HTTP {status_code}'}

            final_url = str(next_url or validated_url)
            validate_url(final_url, whitelist, resolved_hosts)
            return success_payload(original_url, final_url, content_type, data, byte_truncated)

        return {'status': 'error', 'url': original_url, 'error': 'too many redirects'}
    except Exception as exc:
        return {'status': 'error', 'url': original_url, 'error': str(exc)}
