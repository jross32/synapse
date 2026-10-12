"""Keep release unit/integration tests deterministic without real cloud account writes."""
import urllib.request
import urllib.error
import urllib.parse

_original_urlopen = urllib.request.urlopen

def _offline_urlopen(request, *args, **kwargs):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    hostname = urllib.parse.urlparse(url).hostname
    if hostname not in ("localhost", "127.0.0.1", "::1", None):
        raise urllib.error.URLError("External network disabled in release tests; mock the service or use lifecycle proof")
    return _original_urlopen(request, *args, **kwargs)

urllib.request.urlopen = _offline_urlopen
