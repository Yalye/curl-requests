"""
Helpers to build ordered curl headers and keep their memory alive.

This module assumes you have `lib` and `ffi` available from your cffi wrapper
(e.g., curlx_browse.wrapper._wrapper.lib, ffi). The Session will pass them in.
"""

from collections import OrderedDict
from urllib.parse import urlparse


def normalize_headers(headers, default_host=None):
    """
    Accept headers as:
      - dict
      - OrderedDict
      - list/tuple of (k,v)

    Return a list of (name, value) in the desired order.
    If default_host given and 'Host' not provided, it will be inserted first.
    """
    if headers is None:
        headers_list = []
    elif isinstance(headers, (list, tuple)):
        headers_list = list(headers)
    elif isinstance(headers, OrderedDict):
        headers_list = list(headers.items())
    elif isinstance(headers, dict):
        # keep dict insertion order (Python 3.7+ preserves it),
        # but callers should use OrderedDict if they need explicit order.
        headers_list = list(headers.items())
    else:
        raise TypeError("headers must be dict, OrderedDict, or list of tuples")

    # Ensure Host is present and first if default_host provided and Host missing
    names = [n.lower() for n, _ in headers_list]
    if default_host and "host" not in names:
        headers_list.insert(0, ("Host", default_host))

    return headers_list


def build_slist(lib, ffi, session_buffers, headers_list):
    """
    Build a curl_slist that preserves header order.

    - lib: cffi-loaded libcurl
    - ffi: cffi ffi
    - session_buffers: a list on the Session instance used to retain references
    - headers_list: list of (name, value) in order

    Returns the cdata pointer for the slist (to pass to CURLOPT_HTTPHEADER).
    The slist must be freed later with lib.curl_slist_free_all(slist).
    """

    slist = ffi.NULL
    # Build header strings in specified order and append to slist.
    for name, value in headers_list:
        header_bytes = f"{name}: {value}".encode("utf-8")
        cbuf = ffi.new("char[]", header_bytes)
        # keep reference so cbuf isn't GC'd while curl holds pointer
        session_buffers.append(cbuf)
        slist = lib.curl_slist_append(slist, cbuf)

    return slist
