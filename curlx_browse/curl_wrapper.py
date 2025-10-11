from wrapper._wrapper import lib, ffi
from .exceptions import Timeout, ConnectTimeout, ReadTimeout, CurlRequestException
from urllib.parse import urlencode, urlparse
from response import CurlResponse

class CurlWrapper:

    def __init__(self):
        self._buffers = []

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

    def perform_request(self, curl, method, url, headers=None, data=None, json=None, files=None, timeout=30,
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

        # Set the request headers, if provided
        header_list = ffi.NULL
        if headers:
            for k, v in headers.items():
                hdr = f"{k}: {v}".encode()
                header_list = lib.curl_slist_append(header_list, ffi.new("char[]", hdr))
            lib._curl_easy_setopt(curl, lib.CURLOPT_HTTPHEADER, header_list)

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


if __name__ == '__main__':
    result = lib.add(2, 3)
    print(result)
