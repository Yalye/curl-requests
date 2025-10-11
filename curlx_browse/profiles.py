"""
Browser header profiles.

Each profile provides:
- an ordered list of (header_name, header_value) tuples
- intended to mimic a particular browser/version/platform
"""

from collections import OrderedDict

# Example: Chrome Desktop (approximate, Chrome 122-ish)
# Header order and content derived from typical Chrome requests.
# You can extend or add mobile/Firefox profiles.
CHROME_DESKTOP_122 = [
    ("Host", None),  # placeholder, set per-request
    ("Connection", "keep-alive"),
    ("Upgrade-Insecure-Requests", "1"),
    # Sec-CH-UA and friends often appear early in modern browsers
    ("Sec-CH-UA", '"Chromium";v="122", "Not A(Brand";v="24", "Google Chrome";v="122"'),
    ("Sec-CH-UA-Mobile", "?0"),
    ("Sec-CH-UA-Platform", '"Windows"'),
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0.0.0 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-User", "?1"),
    ("Sec-Fetch-Dest", "document"),
    ("Referer", None),  # optional
    ("Accept-Encoding", "gzip, deflate, br"),
    ("Accept-Language", "en-US,en;q=0.9"),
]

# Helper: return an OrderedDict where None values are placeholders
def get_chrome_desktop_122(host=None, referer=None):
    """
    Return an OrderedDict of headers for Chrome-122 desktop.
    Provide host and optionally referer to fill placeholders.
    """
    od = OrderedDict()
    for name, value in CHROME_DESKTOP_122:
        if name == "Host":
            od[name] = host or ""
        elif name == "Referer":
            if referer is not None:
                od[name] = referer
            # else: skip referer if None
        else:
            od[name] = value
    # remove any empty/ref None entries
    return OrderedDict((k, v) for k, v in od.items() if v is not None and v != "")
