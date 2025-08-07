from curl_requests._wrapper import lib, ffi
from curl_requests.exceptions import Timeout, ConnectTimeout, ReadTimeout, CurlRequestException
from urllib.parse import urlencode
from response import CurlResponse

class CurlWrapper:
    def setopt(self, curl, option, value):
        if isinstance(value, str):
            val = ffi.new("char[]", value.encode())
        elif isinstance(value, bytes):
            val = ffi.new("char[]", value)
        elif isinstance(value, int):
            val = ffi.new("long *", value)
        elif value is None:
            val = ffi.NULL
        else:
            val = value  # assume already cdata
        lib._curl_easy_setopt(curl, option, val)

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

    def perform_request(self, method, url, headers=None, data=None, json=None, files=None, timeout=30):
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

        # Initialize a new curl handle
        curl = lib.curl_easy_init()
        if curl == ffi.NULL:
            raise RuntimeError("Failed to init curl")

        # Set the URL for the request
        lib._curl_easy_setopt(curl, lib.CURLOPT_URL, ffi.new("char[]", url.encode()))
        lib._curl_easy_setopt(curl, lib.CURLOPT_CUSTOMREQUEST, ffi.new("char[]", method.encode()))

        # Disable SSL verification (optional, but necessary for some environments)
        self.setopt(curl, lib.CURLOPT_SSL_VERIFYHOST, 0)
        self.setopt(curl, lib.CURLOPT_SSL_VERIFYPEER, 0)

        # Set the request headers, if provided
        header_list = ffi.NULL
        if headers:
            for k, v in headers.items():
                hdr = f"{k}: {v}".encode()
                header_list = lib.curl_slist_append(header_list, ffi.new("char[]", hdr))
            lib._curl_easy_setopt(curl, lib.CURLOPT_HTTPHEADER, header_list)

        # Handle POST data
        if method == "POST" and data:
            lib._curl_easy_setopt(curl, lib.CURLOPT_POST, 1)
            if isinstance(data, dict):
                post_data = urlencode(data).encode()   # URL encode the data if it's a dict
            else:
                post_data = data.encode() if isinstance(data, str) else data   # Handle string data
            lib._curl_easy_setopt(curl, lib.CURLOPT_POSTFIELDS, ffi.new("char[]", post_data))

        # Set timeout
        if timeout:
            self.setopt(curl, lib.CURLOPT_CONNECTTIMEOUT, timeout)
            self.setopt(curl, lib.CURLOPT_TIMEOUT, timeout)

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

        # Get the header
        raw_headers = ffi.new("char **")
        lib.curl_easy_getinfo(curl, lib.CURLINFO_HEADERDATA, raw_headers)


        # Clean up the curl handle
        lib.curl_easy_cleanup(curl)

        # Extract cookies from Set-Cookie headers
        cookie_dict = {}
        for line in header_buf:
            if line.lower().startswith("set-cookie:"):
                parts = line[11:].split(";", 1)[0]  # Get only key=value
                if "=" in parts:
                    k, v = parts.strip().split("=", 1)
                    cookie_dict[k] = v

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
