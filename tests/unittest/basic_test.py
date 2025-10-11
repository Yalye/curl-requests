import pytest

from curlx_browse.session import CurlSession
from curlx_browse.exceptions import ReadTimeout, ConnectTimeout, Timeout

@pytest.fixture
def curl_session():
    s = CurlSession()
    yield s
    s.close()

def test_get(curl_session):
    r3 = curl_session.get("https://httpbin.org/get")
    print(r3.status_code)
    print(r3.json())

def test_get_params(curl_session):
    params = {
        "q": "test",
        "page": "1"
    }
    headers = {
        "User-Agent": "test/1.0",
        "X-Test-Header": "my-value"
    }
    r = curl_session.get('https://httpbin.org/get', params=params, headers=headers, )
    print(r.status_code)
    print(r.json())
    print(r.content)

def test_get_timeout(curl_session):
    try:
        r = curl_session.get('https://httpbin.org/delay/5', timeout=1)
    except ReadTimeout as e:
        print("Server took too long to respond (read timeout)")
    except ConnectTimeout:
        print("Couldn't connect to server (connect timeout)")
    except Timeout:
        print("General timeout error")
    except Exception as e:
        print(f"Caught exception type: {type(e)} - {e}")

def test_get_headers(curl_session):
    r1 = curl_session.get("https://httpbin.org/headers")
    print("=== Default Headers ===")
    print(r1.text)

    r2 = curl_session.get("https://httpbin.org/headers", headers={
        "User-Agent": "Custom-UA/2.0",
        "X-Test": "yes"
    })
    print("\n=== Custom Headers ===")
    print(r2.text)

def test_get_cookies(curl_session):
    resp1 = curl_session.get('https://httpbin.org/cookies/set?testcookie=value123')
    print("Cookies after first request:", resp1.cookies)

    resp2 = curl_session.get('https://httpbin.org/cookies')
    print("Second response content:", resp2.content.decode())


def test_redirection(curl_session):
    resp = curl_session.get("https://httpbin.org/redirect/2", allow_redirects=True)
    print(resp.status_code)  # 200
    print(resp.content[:200])

    resp_no_redirect = curl_session.get("https://httpbin.org/redirect/2", allow_redirects=False)
    print(resp_no_redirect.status_code)  # 302

def test_get_with_proxies(curl_session):
    proxies = {
        'http': 'http://',
        'https': 'http://'
    }
    resp = curl_session.get('http://ip-api.com/json', proxies=proxies)
    print(resp.content)


def test_post_json(curl_session):
    url = "https://httpbin.org/post"
    json_data = {"name": "ChatGPT", "type": "test"}

    resp = curl_session.post(url, json=json_data)

    assert resp.status_code == 200
    json_response = resp.json()
    print(json_response)
    assert json_response["json"]["type"] == "test"

def test_post_data(curl_session):
    url = "https://httpbin.org/post"
    data = {"name": "ChatGPT", "type": "test"}

    resp = curl_session.post(url, data=data)

    assert resp.status_code == 200
    json_response = resp.json()
    print(json_response)
    assert json_response["form"]["type"] == "test"

def test_post_bytes(curl_session):
    url = "https://httpbin.org/post"
    data = b"\x00\x01\x02binary"

    resp = curl_session.post(url, data=data)

    assert resp.status_code == 200
    json_response = resp.json()
    print(json_response)

def test_post_file(curl_session):
    url = "https://httpbin.org/post"
    files = {"file1": "C:\\Users\\admin\\Desktop\\a.txt"}
    resp = curl_session.post(url, files=files)

    assert resp.status_code == 200
    json_response = resp.json()
    print(json_response)

def test_ordered_headers(curl_session):
    curl_session.set_profile(profile_name='chrome122')
    r1 = curl_session.get("https://httpbin.org/headers")
    print("=== Default Headers ===")
    print(r1.text)

    r2 = curl_session.get("https://httpbin.org/headers", headers={
        "User-Agent": "Custom-UA/2.0",
        "X-Test": "yes"
    })
    print("\n=== Custom Headers ===")
    print(r2.text)
