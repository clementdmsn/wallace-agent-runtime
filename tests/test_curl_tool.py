from __future__ import annotations

import json

import pytest

from config import Settings
from tools import curl_tool


def configure_curl(tmp_path, monkeypatch, domains=None):
    whitelist_path = tmp_path / 'state' / 'curl_whitelist.json'
    settings = Settings(
        sandbox_dir=tmp_path / 'sandbox',
        curl_whitelist_path=whitelist_path,
    )
    monkeypatch.setattr(curl_tool, 'SETTINGS', settings)
    if domains is not None:
        whitelist_path.parent.mkdir(parents=True)
        whitelist_path.parent.chmod(0o700)
        whitelist_path.write_text(json.dumps({'domains': domains}), encoding='utf-8')
        whitelist_path.chmod(0o600)
    return settings


def allow_public_dns(monkeypatch):
    monkeypatch.setattr(
        curl_tool.socket,
        'getaddrinfo',
        lambda *args, **kwargs: [(curl_tool.socket.AF_INET, curl_tool.socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))],
    )


def test_load_whitelist_missing_file_is_empty(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch)

    assert curl_tool.load_whitelist() == set()


def test_add_domain_to_whitelist_persists_sorted_unique_domains(tmp_path, monkeypatch):
    settings = configure_curl(tmp_path, monkeypatch, ['docs.python.org'])

    result = curl_tool.add_domain_to_whitelist('Platform.OpenAI.com')
    curl_tool.add_domain_to_whitelist('docs.python.org')

    assert result == {'status': 'ok', 'domain': 'platform.openai.com'}
    payload = json.loads(settings.curl_whitelist_path.read_text(encoding='utf-8'))
    assert payload == {'domains': ['docs.python.org', 'platform.openai.com']}


def test_whitelist_path_rejects_sandbox_location(tmp_path, monkeypatch):
    settings = Settings(
        sandbox_dir=tmp_path / 'sandbox',
        curl_whitelist_path=tmp_path / 'sandbox' / 'curl_whitelist.json',
    )
    monkeypatch.setattr(curl_tool, 'SETTINGS', settings)

    with pytest.raises(ValueError, match='must not be inside the sandbox'):
        curl_tool.whitelist_path()


def test_whitelist_storage_rejects_group_accessible_file(tmp_path, monkeypatch):
    settings = configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    settings.curl_whitelist_path.chmod(0o640)

    with pytest.raises(ValueError, match='must not be accessible'):
        curl_tool.load_whitelist()


@pytest.mark.parametrize(
    'url,error',
    [
        ('http://docs.python.org/', 'only https URLs are allowed'),
        ('https://user:pass@docs.python.org/', 'URL userinfo is not allowed'),
        ('https://docs.python.org/path#frag', 'URL fragments are not allowed'),
        ('https://docs.python.org:444/', 'only the default https port is allowed'),
        ('https://93.184.216.34/', 'IP literal URLs are not allowed'),
    ],
)
def test_validate_url_rejects_unsafe_urls(tmp_path, monkeypatch, url, error):
    configure_curl(tmp_path, monkeypatch)
    allow_public_dns(monkeypatch)

    with pytest.raises(ValueError, match=error):
        curl_tool.validate_url(url, {'docs.python.org', '93.184.216.34'})


def test_validate_url_rejects_non_whitelisted_subdomain(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch)
    allow_public_dns(monkeypatch)

    with pytest.raises(PermissionError) as exc:
        curl_tool.validate_url('https://sub.example.com/docs', {'example.com'})

    assert str(exc.value) == 'sub.example.com'


def test_validate_url_rejects_private_dns_targets(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch)
    monkeypatch.setattr(
        curl_tool.socket,
        'getaddrinfo',
        lambda *args, **kwargs: [(curl_tool.socket.AF_INET, curl_tool.socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))],
    )

    with pytest.raises(ValueError, match='private or unsafe'):
        curl_tool.validate_url('https://docs.python.org/', {'docs.python.org'})


def test_curl_url_requires_approval_for_non_whitelisted_domain(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch)

    result = curl_tool.curl_url('https://docs.python.org/3/')

    assert result['status'] == 'approval_required'
    assert result['domain'] == 'docs.python.org'
    assert result['url'] == 'https://docs.python.org/3/'
    assert result['approval_id'].startswith('curl:docs.python.org:')


def test_curl_url_upgrades_http_input_to_https_before_fetching(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)

    def fake_fetch_once(url, domain, addresses):
        assert url == 'https://docs.python.org/3/howto/urllib2.html'
        return (200, 'text/plain', b'legacy docs', False, url)

    monkeypatch.setattr(curl_tool, 'fetch_once', fake_fetch_once)

    result = curl_tool.curl_url('http://docs.python.org/3/howto/urllib2.html')

    assert result['status'] == 'ok'
    assert result['url'] == 'http://docs.python.org/3/howto/urllib2.html'
    assert result['final_url'] == 'https://docs.python.org/3/howto/urllib2.html'
    assert result['content'] == 'legacy docs'


def test_curl_url_returns_compact_extracted_html(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)

    def fake_fetch_once(url, domain, addresses):
        assert domain == 'docs.python.org'
        assert addresses == ['93.184.216.34']
        return (
            200,
            'text/html; charset=utf-8',
            b'<html><head><title>Python Docs</title><style>.x{}</style></head>'
            b'<body><nav>Home</nav><main><h1>Library</h1><script>alert(1)</script><p>Useful text.</p></main></body></html>',
            False,
            url,
        )

    monkeypatch.setattr(curl_tool, 'fetch_once', fake_fetch_once)

    result = curl_tool.curl_url('https://docs.python.org/3/')

    assert result == {
        'status': 'ok',
        'url': 'https://docs.python.org/3/',
        'final_url': 'https://docs.python.org/3/',
        'title': 'Python Docs',
        'content': 'Library\nUseful text.',
        'truncated': False,
    }
    assert '<script>' not in result['content']


def test_curl_url_truncates_content(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)
    monkeypatch.setattr(curl_tool, 'MAX_CURL_CONTENT_CHARS', 5)
    monkeypatch.setattr(
        curl_tool,
        'fetch_once',
        lambda url, domain, addresses: (200, 'text/plain', b'123456789', False, url),
    )

    result = curl_tool.curl_url('https://docs.python.org/3/')

    assert result['status'] == 'ok'
    assert result['content'] == '12345'
    assert result['truncated'] is True


def test_curl_url_blocks_redirect_to_non_whitelisted_domain(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)
    calls = []

    def fake_fetch_once(url, domain, addresses):
        calls.append(url)
        return (302, 'text/html', b'', False, 'https://evil.example/docs')

    monkeypatch.setattr(curl_tool, 'fetch_once', fake_fetch_once)

    result = curl_tool.curl_url('https://docs.python.org/3/')

    assert result['status'] == 'approval_required'
    assert result['domain'] == 'evil.example'
    assert calls == ['https://docs.python.org/3/']


def test_curl_url_reports_http_errors_without_body(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)
    monkeypatch.setattr(
        curl_tool,
        'fetch_once',
        lambda url, domain, addresses: (404, 'text/html', b'<h1>not found</h1>', False, url),
    )

    result = curl_tool.curl_url('https://docs.python.org/missing')

    assert result == {
        'status': 'error',
        'url': 'https://docs.python.org/missing',
        'error': 'HTTP 404',
    }


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv(self, size):
        if not self.chunks:
            return b''
        chunk = self.chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self.chunks.insert(0, chunk[size:])
        return chunk[:size]


def test_parse_headers_and_request_target_cover_query_paths():
    assert curl_tool.parse_headers('Content-Type: text/plain\r\nX-Test: yes\r\nbroken') == {
        'content-type': 'text/plain',
        'x-test': 'yes',
    }
    assert curl_tool.request_target('https://docs.python.org') == '/'
    assert curl_tool.request_target('https://docs.python.org/search?q=ssl') == '/search?q=ssl'


def test_recv_until_headers_splits_initial_body():
    sock = FakeSocket([b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nbody'])

    headers, body = curl_tool.recv_until_headers(sock)

    assert headers == b'HTTP/1.1 200 OK\r\nContent-Type: text/plain'
    assert body == b'body'


def test_recv_until_headers_rejects_oversized_headers(monkeypatch):
    monkeypatch.setattr(curl_tool, 'MAX_CURL_BYTES', 5)
    sock = FakeSocket([b'abcdef'])

    with pytest.raises(curl_tool.CurlFetchError, match='response headers are too large'):
        curl_tool.recv_until_headers(sock)


def test_read_http_body_respects_content_length():
    sock = FakeSocket([b'def', b'ignored'])

    data, truncated = curl_tool.read_http_body(sock, b'abc', {'content-length': '6'})

    assert data == b'abcdef'
    assert truncated is False


def test_read_http_body_truncates_unknown_length(monkeypatch):
    monkeypatch.setattr(curl_tool, 'MAX_CURL_BYTES', 4)
    sock = FakeSocket([b'cdef'])

    data, truncated = curl_tool.read_http_body(sock, b'ab', {})

    assert data == b'abcd'
    assert truncated is True


def test_read_chunked_body_reads_chunks_and_extensions():
    sock = FakeSocket([b'4;ext=value\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n'])

    data, truncated = curl_tool.read_chunked_body(sock, b'')

    assert data == b'Wikipedia'
    assert truncated is False


def test_read_chunked_body_reports_invalid_and_incomplete_responses():
    with pytest.raises(curl_tool.CurlFetchError, match='invalid chunked response'):
        curl_tool.read_chunked_body(FakeSocket([]), b'zz\r\n')

    with pytest.raises(curl_tool.CurlFetchError, match='incomplete chunked response'):
        curl_tool.read_chunked_body(FakeSocket([]), b'4\r\nWi')


def test_success_payload_marks_byte_truncation():
    result = curl_tool.success_payload('https://docs.python.org', 'https://docs.python.org', 'text/plain', b'hello', True)

    assert result['status'] == 'ok'
    assert result['content'] == 'hello'
    assert result['truncated'] is True


def test_curl_url_reports_missing_redirect_location(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)
    monkeypatch.setattr(
        curl_tool,
        'fetch_once',
        lambda url, domain, addresses: (302, 'text/html', b'', False, None),
    )

    result = curl_tool.curl_url('https://docs.python.org/3/')

    assert result == {
        'status': 'error',
        'url': 'https://docs.python.org/3/',
        'error': 'redirect response missing location',
    }


def test_curl_url_reports_too_many_redirects(tmp_path, monkeypatch):
    configure_curl(tmp_path, monkeypatch, ['docs.python.org'])
    allow_public_dns(monkeypatch)
    monkeypatch.setattr(curl_tool, 'MAX_REDIRECTS', 1)
    monkeypatch.setattr(
        curl_tool,
        'fetch_once',
        lambda url, domain, addresses: (302, 'text/html', b'', False, '/next'),
    )

    result = curl_tool.curl_url('https://docs.python.org/3/')

    assert result == {
        'status': 'error',
        'url': 'https://docs.python.org/3/',
        'error': 'too many redirects',
    }
