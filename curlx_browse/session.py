from urllib.parse import urlencode, urlparse
from wrapper._wrapper import lib, ffi
from .exceptions import Timeout, ConnectTimeout, ReadTimeout, CurlRequestException
from .curl_wrapper import CurlWrapper
from .response import CurlResponse
from .headers import normalize_headers, build_slist
from .profiles import get_chrome_desktop_122

class CurlSession:
    def __init__(self):
        # Initialize a unique curl easy handle per session
        self.curl = lib.curl_easy_init()
        if self.curl == ffi.NULL:
            raise RuntimeError("Failed to init curl")

        # Enable libcurl cookie engine in memory (empty string)
        lib._curl_easy_setopt(self.curl, lib.CURLOPT_COOKIEFILE, ffi.new("char[]", b""))

        # Optional: save cookies to a file during session lifecycle
        # lib._curl_easy_setopt(self.curl, lib.CURLOPT_COOKIEJAR, ffi.new("char[]", b"cookies.txt"))

        self.cookies = {
            # "cookieee":"eeeee"
        }

        self.proxies = None

        # self.timeout = 30
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }

        # holder to keep alive any ffi buffers (post bodies, header names, slists...)
        self._buffers = []
        self._slist = ffi.NULL  # current header slist pointer (if any)

    def get_cookie_header(self):
        # Convert stored cookies to a Cookie header string
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def _apply_headers(self, headers, url):
        # clear previous slist if any
        if self._slist != ffi.NULL:
            lib.curl_slist_free_all(self._slist)
            self._slist = ffi.NULL
        # reset buffer list for this request
        self._buffers = []

        parsed = urlparse(url)
        host = parsed.netloc
        headers_list = normalize_headers(headers, default_host=host)

        # build slist preserving order and keep cdata alive in self._buffers
        self._slist = build_slist(lib, ffi, self._buffers, headers_list)
        if self._slist != ffi.NULL:
            # set headers on the curl handle (note: using the session's curl handle)
            lib._curl_easy_setopt(self.curl, lib.CURLOPT_HTTPHEADER, self._slist)

    def set_profile(self, profile_name="chrome122", referer=None):
        """
        Set a built-in browser-like profile as session default headers/order.
        Use get_chrome_desktop_122 to get OrderedDict of headers.
        """
        if profile_name == "chrome122":
            self._profile_headers = get_chrome_desktop_122(host=None, referer=referer)
        else:
            raise ValueError("unknown profile")

    def perform_request(self,
        method,
        url,
        params=None,
        data=None,
        headers=None,
        cookies=None,
        files=None,
        auth=None,
        timeout=None,
        allow_redirects=True,
        proxies=None,
        hooks=None,
        stream=None,
        verify=None,
        cert=None,
        json=None):
        """Constructs a :class:`Request <Request>`, prepares it and sends it.
        Returns :class:`Response <Response>` object.

        :param method: method for the new :class:`Request` object.
        :param url: URL for the new :class:`Request` object.
        :param params: (optional) Dictionary or bytes to be sent in the query
            string for the :class:`Request`.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param json: (optional) json to send in the body of the
            :class:`Request`.
        :param headers: (optional) Dictionary of HTTP Headers to send with the
            :class:`Request`.
        :param cookies: (optional) Dict or CookieJar object to send with the
            :class:`Request`.
        :param files: (optional) Dictionary of ``'filename': file-like-objects``
            for multipart encoding upload.
        :param auth: (optional) Auth tuple or callable to enable
            Basic/Digest/Custom HTTP Auth.
        :param timeout: (optional) How long to wait for the server to send
            data before giving up, as a float, or a :ref:`(connect timeout,
            read timeout) <timeouts>` tuple.
        :type timeout: float or tuple
        :param allow_redirects: (optional) Set to True by default.
        :type allow_redirects: bool
        :param proxies: (optional) Dictionary mapping protocol or protocol and
            hostname to the URL of the proxy.
        :param stream: (optional) whether to immediately download the response
            content. Defaults to ``False``.
        :param verify: (optional) Either a boolean, in which case it controls whether we verify
            the server's TLS certificate, or a string, in which case it must be a path
            to a CA bundle to use. Defaults to ``True``. When set to
            ``False``, requests will accept any TLS certificate presented by
            the server, and will ignore hostname mismatches and/or expired
            certificates, which will make your application vulnerable to
            man-in-the-middle (MitM) attacks. Setting verify to ``False``
            may be useful during local development or testing.
        :param cert: (optional) if String, path to ssl client cert file (.pem).
            If Tuple, ('cert', 'key') pair.
        :rtype: requests.Response
        """
        headers = {**self.default_headers, **(headers or {})}

        if self.cookies:
            cookie_header = self.get_cookie_header()
            headers = headers or {}
            headers.setdefault("Cookie", cookie_header)

        # Set the request headers, if provided
        header_list = ffi.NULL
        if headers:
            for k, v in headers.items():
                hdr = f"{k}: {v}".encode()
                header_list = lib.curl_slist_append(header_list, ffi.new("char[]", hdr))

        # merge profile headers with provided headers; profile headers provide order
        if hasattr(self, "_profile_headers"):
            # start with profile (OrderedDict) then override with user headers
            merged = list(self._profile_headers.items())
            if headers:
                # overlay user headers but preserve profile base order:
                # remove any profile keys replaced by user and append user headers in user order
                user_items = list(headers.items()) if isinstance(headers, dict) else list(headers)
                profile_keys = {k.lower() for k, _ in merged}
                # override values
                for i, (k, v) in enumerate(merged):
                    if k.lower() in {uk.lower() for uk, _ in user_items}:
                        # replace with user's value (keep order)
                        merged[i] = (k, dict(user_items)[k])
                # append user-only headers
                for uk, uv in user_items:
                    if uk.lower() not in profile_keys:
                        merged.append((uk, uv))
            headers_list = merged
        else:
            headers_list = headers

        # apply headers (this builds slist and sets CURLOPT_HTTPHEADER)
        self._apply_headers(headers_list, url)

        if params:
            query = urlencode(params, doseq=True)
            connector = '&' if '?' in url else '?'
            url += connector + query

        res = self.perform_request_with_curl(self.curl, method=method, url=url, headers=headers, timeout=timeout, data=data,
                                   json=json, files=files,
                                   allow_redirects=allow_redirects, proxies=proxies)
        return res


    def get(self, url, **kwargs):
        r"""Sends a GET request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """
        return self.perform_request('GET', url, **kwargs)


    def options(self, url, **kwargs):
        r"""Sends a OPTIONS request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        kwargs.setdefault("allow_redirects", True)
        return self.request("OPTIONS", url, **kwargs)

    def head(self, url, **kwargs):
        r"""Sends a HEAD request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        kwargs.setdefault("allow_redirects", False)
        return self.request("HEAD", url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        r"""Sends a POST request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param json: (optional) json to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """
        # Convert dict to x-www-form-urlencoded if data is dict
        if data and isinstance(data, dict):
            data = urlencode(data)
            self.default_headers["Content-Type"] = "application/x-www-form-urlencoded"

        # If json is provided, encode as JSON and set header
        if json is not None:
            import json as jsonlib
            data = jsonlib.dumps(json).encode('UTF-8')
            self.default_headers["Content-Type"] = "application/json"

        return self.perform_request('POST', url, data=data, json=json, **kwargs)


    def close(self):
        if self.curl != ffi.NULL:
            lib.curl_easy_cleanup(self.curl)
            self.curl = ffi.NULL

    def setopt(self, curl, option, value):
        if isinstance(value, str):
            buf = ffi.new("char[]", value.encode())
            self._buffers.append(buf)
            lib._curl_easy_setopt(curl, option, buf)
        elif isinstance(value, bytes):
            buf = ffi.new("char[]", value)
            self._buffers.append(buf)
            lib._curl_easy_setopt(curl, option, buf)
        elif isinstance(value, int):
            val = ffi.new("long *", value)
            lib._curl_easy_setopt(curl, option, val)
        elif value is None:
            lib._curl_easy_setopt(curl, option, ffi.NULL)
        else:
            # assume already cdata
            self._buffers.append(value)
            lib._curl_easy_setopt(curl, option, value)


    def prepare_body(self, data=None, json=None, files=None):
        if json is not None:
            body = json.dumps(json).encode("utf-8")
            content_type = "application/json"
        elif isinstance(data, dict):
            body = urlencode(data).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        elif isinstance(data, str):
            body = data.encode("utf-8")
            content_type = "text/plain"
        elif files:
            raise NotImplementedError("multipart not yet implemented")
        else:
            body = b""
            content_type = "application/octet-stream"
        return body, content_type

    def apply_proxies(self, curl, proxies, url):
        if not proxies:
            return

        scheme = urlparse(url).scheme
        proxy_url = proxies.get(scheme)
        if not proxy_url:
            return

        parsed = urlparse(proxy_url)

        self.setopt(curl, lib.CURLOPT_PROXY, parsed.hostname)

        if parsed.port:
            self.setopt(curl, lib.CURLOPT_PROXYPORT, parsed.port)

        if parsed.scheme == 'http':
            self.setopt(curl, lib.CURLOPT_PROXYTYPE, lib.CURLPROXY_HTTP)
        elif parsed.scheme in ('socks4', 'socks4a'):
            self.setopt(curl, lib.CURLOPT_PROXYTYPE, lib.PROXYTYPE_SOCKS4)
        elif parsed.scheme == 'socks5':
            self.setopt(curl, lib.CURLOPT_PROXYTYPE, lib.PROXYTYPE_SOCKS5)
        elif parsed.scheme == 'socks5h':
            self.setopt(curl, lib.CURLOPT_PROXYTYPE, lib.PROXYTYPE_SOCKS5_HOSTNAME)

        if parsed.username or parsed.password:
            userpwd = f"{parsed.username or ''}:{parsed.password or ''}"
            self.setopt(curl, lib.CURLOPT_PROXYUSERPWD, userpwd)

    def perform_request_with_curl(self, curl, method, url, headers=None, data=None, json=None, files=None, timeout=30,
                        allow_redirects=True, **kwargs):
        """
        Perform an HTTP request using libcurl (via curl_cffi).

        Args:
            method (str): The HTTP method (GET, POST, etc.)
            url (str): The target URL
            headers (dict, optional): Headers to be sent with the request
            data (str or dict, optional): Data to be sent with the request (for POST)
            json (dict, optional): JSON data (if method is POST, data is JSON)
            files (dict, optional): Files to be uploaded (for multipart/form-data)
            timeout (int, optional): Timeout for the request in seconds (default 30)

        Returns:
            CurlResponse: A Response object containing status code, content, and headers.

        Raises:
            RuntimeError: If curl initialization or the request fails.
        """
        self._buffers = []

        # Set the URL for the request
        lib._curl_easy_setopt(curl, lib.CURLOPT_URL, ffi.new("char[]", url.encode()))
        lib._curl_easy_setopt(curl, lib.CURLOPT_CUSTOMREQUEST, ffi.new("char[]", method.encode()))

        # Disable SSL verification (optional, but necessary for some environments)
        self.setopt(curl, lib.CURLOPT_SSL_VERIFYHOST, 0)
        self.setopt(curl, lib.CURLOPT_SSL_VERIFYPEER, 0)

        # Accept all encoding and unzip
        self.setopt(curl, lib.CURLOPT_ACCEPT_ENCODING, "")

        # Handle POST data
        mime = None
        if method == "POST":
            if files:
                # multipart/form-data
                mime = lib.curl_mime_init(curl)
                for field_name, file_path in files.items():
                    part = lib.curl_mime_addpart(mime)
                    lib.curl_mime_name(part, field_name.encode())
                    lib.curl_mime_filedata(part, file_path.encode())
                lib._curl_easy_setopt(curl, lib.CURLOPT_MIMEPOST, mime)
            elif data:
                self.setopt(curl, lib.CURLOPT_POST, 1)
                if isinstance(data, dict):
                    post_data = urlencode(data).encode()   # URL encode the data if it's a dict
                else:
                    post_data = data.encode() if isinstance(data, str) else data   # Handle string data
                self.setopt(curl, lib.CURLOPT_POSTFIELDS, post_data)
                self.setopt(curl, lib.CURLOPT_POSTFIELDSIZE, len(post_data))

        # Set timeout
        if timeout:
            self.setopt(curl, lib.CURLOPT_CONNECTTIMEOUT, timeout)
            self.setopt(curl, lib.CURLOPT_TIMEOUT, timeout)

        # Redirect support
        if allow_redirects:
            self.setopt(curl, lib.CURLOPT_FOLLOWLOCATION, 1)
            self.setopt(curl, lib.CURLOPT_MAXREDIRS, 10)
        else:
            self.setopt(curl, lib.CURLOPT_FOLLOWLOCATION, 0)

        # Apply proxies
        self.apply_proxies(curl, kwargs.get("proxies"), url)

        # Write callback function to capture the response body
        buf = []
        @ffi.callback("size_t(char *, size_t, size_t, void *)")
        def write_cb(ptr, size, nmemb, userdata):
            """
            Callback function that appends the response data to a buffer.

            Args:
                ptr (cdata): The pointer to the response data in memory
                size (int): The size of each data unit
                nmemb (int): The number of data units
                userdata (object): Custom user data (not used here)

            Returns:
                int: The number of bytes processed
            """
            content = ffi.string(ptr, size * nmemb)
            buf.append(content)
            return size * nmemb

        header_buf = []
        @ffi.callback("size_t(char *, size_t, size_t, void *)")
        def header_cb(ptr, size, nmemb, userdata):
            line = ffi.string(ptr, size * nmemb).decode()
            header_buf.append(line)
            return size * nmemb

        # Set the callback for writing response data
        lib._curl_easy_setopt(curl, lib.CURLOPT_WRITEFUNCTION, write_cb)
        lib._curl_easy_setopt(curl, lib.CURLOPT_HEADERFUNCTION, header_cb)

        # Perform the request
        res = lib.curl_easy_perform(curl)
        if res != 0:
            if res == lib.CURLE_OPERATION_TIMEDOUT:
                raise ReadTimeout("Read timeout occurred")
            elif res == lib.CURLE_COULDNT_CONNECT:
                raise ConnectTimeout("Connection timed out")
            elif res == lib.CURLE_COULDNT_RESOLVE_HOST:
                raise ConnectTimeout("DNS resolution failed")
            else:
                raise CurlRequestException(f"curl failed with code {res}")

        # Get the response status code
        status_code = ffi.new("long *")
        lib.curl_easy_getinfo(curl, lib.CURLINFO_RESPONSE_CODE, status_code)

        # Clean up the curl handle
        # lib.curl_easy_cleanup(curl)

        if mime:
            lib.curl_mime_free(mime)

        # Extract cookies from Set-Cookie headers
        cookie_dict = {}
        for line in header_buf:
            if line.lower().startswith("set-cookie:"):
                parts = line[11:].split(";", 1)[0]  # Get only key=value
                if "=" in parts:
                    k, v = parts.strip().split("=", 1)
                    cookie_dict[k] = v

        self._buffers = []

        # Return a CurlResponse object with the response status, content, and other data
        resp = CurlResponse(
            status_code=status_code[0],  # HTTP status code
            content=b"".join(buf),  # Response content
            headers={},  # Headers (parse headers if needed)
            url=url,  # Final URL after redirects
            cookies=cookie_dict,  # Add cookies handling if needed
            raw=None  # Optional raw data (e.g., curl handle)
        )
        return resp

