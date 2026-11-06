"""Portable isolated test entrypoint; no site/.pth or dotenv startup."""

import os
import sys

if not sys.flags.no_site or not sys.flags.isolated:
    raise SystemExit("Owned Python bootstrap requires isolated no-site startup")


def deny_dotenv(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        name = os.fsdecode(args[0]).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name == ".env" or name.startswith(".env."):
            raise PermissionError("Dotenv access forbidden in acceptance children")
    if os.environ.get("MARKETLAB_PHASE6_OFFLINE_GUARD") == "1" and event in {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
    }:
        raise PermissionError("Network forbidden in synthetic guard checks")


sys.addaudithook(deny_dotenv)

import sysconfig  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# With Python 3.13, -S can leave sys.prefix at the base interpreter. Preserve
# the executable's venv path (including bin/python symlinks) instead of resolving it.
executable_folder = Path(sys.executable).absolute().parent
prefix = (
    executable_folder.parent
    if executable_folder.name.casefold() in {"bin", "scripts"}
    else executable_folder
)
path_vars = {"base": str(prefix), "platbase": str(prefix)}
sys.path[:0] = list(
    dict.fromkeys(
        [
            sysconfig.get_path("purelib", vars=path_vars),
            sysconfig.get_path("platlib", vars=path_vars),
            str(ROOT / "src"),
        ]
    )
)
os.environ["AWS_CONFIG_FILE"] = os.devnull
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.devnull
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["AWS_SDK_LOAD_CONFIG"] = "false"
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
for name in (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_ROLE_ARN",
    "AWS_ROLE_SESSION_NAME",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
    "AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_S3",
    "AWS_DATA_PATH",
    "AWS_CA_BUNDLE",
    "BOTO_CONFIG",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(name, None)

try:
    from marketlab.config import Settings

    Settings.model_config["env_file"] = None
except BaseException:
    raise SystemExit("Owned configuration guard failed before entrypoint") from None

import multiprocessing.spawn as spawn  # noqa: E402
import runpy  # noqa: E402
import types  # noqa: E402

original_command = spawn.get_command_line


def guarded_command(**kwargs):
    command = original_command(**kwargs)
    return [command[0], "-I", "-S", str(Path(__file__).resolve()), "--", *command[1:]]


spawn.get_command_line = guarded_command
os.environ["MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE"] = "guarded-python-v1"
args = sys.argv[1:]
if args[:1] != ["--"]:
    raise SystemExit("Owned Python bootstrap entrypoint is missing")
args = args[1:]
while args[:1] and args[0] in {"-I", "-S", "-E", "-s"}:
    args = args[1:]
if not args:
    raise SystemExit("Owned Python bootstrap entrypoint is missing")
main = types.ModuleType("__main__")
main.__package__ = None
sys.modules["__main__"] = main
if args[0] == "-c" and len(args) >= 2:
    sys.argv = ["-c", *args[2:]]
    exec(compile(args[1], "<owned-command>", "exec"), main.__dict__)
elif args[0] == "-m" and len(args) >= 2:
    sys.argv = [args[1], *args[2:]]
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
elif not args[0].startswith("-"):
    script = Path(args[0]).resolve()
    if not script.is_relative_to(ROOT):
        raise SystemExit("Owned script entrypoint escapes source workspace")
    sys.argv = [str(script), *args[1:]]
    runpy.run_path(str(script), run_name="__main__")
else:
    raise SystemExit("Unsupported owned Python bootstrap entrypoint")
