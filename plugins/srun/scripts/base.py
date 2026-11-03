"""What every srun module shares: the value-free error, buffer zeroing, the
names in flight, and where srun keeps its files."""
import os

MANIFEST = ".srun.json"
DEFAULT_STORE = "keychain"

# Names of the secret(s) in flight — the ONLY value-adjacent detail the scrubbing
# excepthook is allowed to print.
CURRENT_NAMES = []


class SrunError(Exception):
    """Carries a name-only, value-free message that is safe to print."""


def zero(buf):
    if isinstance(buf, bytearray):
        for i in range(len(buf)):
            buf[i] = 0


def strip_nl(out):
    return out[:-1] if out.endswith(b"\n") else out


def srun_home():
    """~/.srun: the keychain-name index and the personal default store."""
    return os.environ.get("SRUN_HOME") or os.path.expanduser("~/.srun")


def find_manifest(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        cand = os.path.join(d, MANIFEST)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
