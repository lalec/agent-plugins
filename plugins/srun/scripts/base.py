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


def _check_owner(path):
    """A manifest's `cmd` entries run as you, so only trust one that you own and
    no one else can change: the file and its folder yours (the folder may be
    root's) and neither writable by group or others."""
    st, dst = os.stat(path), os.stat(os.path.dirname(path))
    uid = os.getuid()
    if (st.st_uid != uid or dst.st_uid not in (uid, 0)
            or (st.st_mode | dst.st_mode) & 0o022):
        raise SrunError(f"refusing {path}: it and its folder must be yours and "
                        "not writable by others (chown, chmod go-w)")


def find_manifest(start=None):
    """The nearest .srun.json, walking up from the working directory. The walk
    stops at the repo root (a folder holding .git) or at $HOME."""
    d = os.path.abspath(start or os.getcwd())
    home = os.path.expanduser("~")
    while True:
        cand = os.path.join(d, MANIFEST)
        if os.path.isfile(cand):
            _check_owner(cand)
            return cand
        parent = os.path.dirname(d)
        if parent == d or d == home or os.path.exists(os.path.join(d, ".git")):
            return None
        d = parent
