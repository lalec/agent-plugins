"""Masker — redacts each secret value (and its common encodings) from a byte
stream, safely across chunk boundaries, for any number of secrets at once."""
import base64
import json
import urllib.parse

MIN_MASK_LEN = 4             # never mask ultra-short values (would nuke output)
CHUNK = 65536
_URLSAFE = bytes.maketrans(b"+/", b"-_")


def _embedded_b64(raw):
    """The value's base64 inside a longer encoded string (`user:secret` in an
    HTTP Basic header): at each of the 3 byte offsets, only the characters the
    value alone decides. Up to one edge character each side stays unmasked."""
    out = []
    for k in range(3):
        enc = base64.b64encode(b"\0" * k + raw)
        core = enc[-(-8 * k // 6):8 * (k + len(raw)) // 6]
        out += [core, core.translate(_URLSAFE)]
    return out


def mask_forms(name, value):
    label = ("[REDACTED:%s]" % name).encode()
    raw = bytes(value)
    forms = {
        raw,
        base64.b64encode(raw),
        base64.urlsafe_b64encode(raw),
        urllib.parse.quote(raw, safe="").encode(),
        json.dumps(raw.decode("utf-8", "surrogateescape"))[1:-1]
        .encode("utf-8", "surrogateescape"),
        *_embedded_b64(raw),
    }
    return [(f, label) for f in forms if len(f) >= MIN_MASK_LEN]


class Masker:
    def __init__(self, secrets):     # secrets: dict name -> bytearray
        pats = []
        for name, val in secrets.items():
            pats += mask_forms(name, val)
        # Longest patterns first so a value is never half-replaced by one of its
        # own shorter encodings.
        self.patterns = sorted(set(pats), key=lambda p: len(p[0]), reverse=True)
        self.maxlen = max((len(p) for p, _ in self.patterns), default=1)

    def sub(self, data):
        for pat, rep in self.patterns:
            data = data.replace(pat, rep)
        return data

    def stream(self, src, dst):
        # read1 returns as soon as ANY bytes are available; read(CHUNK) on a
        # BufferedReader blocks until 64 KiB or EOF, which stalls interactive
        # children (an MCP stdio server writes one JSON-RPC line, then waits).
        read = getattr(src, "read1", src.read)
        # The held-back tail only exists to catch a match straddling a chunk
        # boundary. When no pattern contains '\n', a chunk ending at a line
        # break cannot split a match — flush through the newline, so
        # line-framed protocols (MCP JSON-RPC) see complete messages promptly.
        nl_safe = not any(b"\n" in p for p, _ in self.patterns)
        carry = b""
        hold = max(self.maxlen - 1, 0)   # a match may straddle a chunk boundary
        while True:
            chunk = read(CHUNK)
            if not chunk:
                break
            data = self.sub(carry + chunk)
            cut = max(len(data) - hold, 0)
            if nl_safe:
                nl = data.rfind(b"\n")
                if nl >= cut:
                    cut = nl + 1
            emit, carry = data[:cut], data[cut:]
            if emit:
                dst.write(emit)
                dst.flush()
        tail = self.sub(carry)
        if tail:
            dst.write(tail)
            dst.flush()
