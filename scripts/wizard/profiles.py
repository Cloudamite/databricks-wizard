"""The profiles a command acts as, and reading the providers' profile
files, each section on its own.

Every command that acts in an account takes its identity from `--aws-profile` and
`--databricks-profile` alone, or, in a pipeline's run, from `--federated`. `act_as` rewrites the process's environment so that
the named profiles are the only identity left in it: the caller's own profile
variables, and every variable that would override a profile, are removed. The
entry point passes `os.environ` itself, because three commands call an SDK in
their own process and the SDKs read `os.environ` directly.

`configparser` lends `[DEFAULT]`'s keys to every section unless its default
section is renamed. A `~/.databrickscfg` whose `DEFAULT` is a workspace profile
would then give every profile that workspace's keys. The Databricks tools read
`DEFAULT` as an ordinary profile, and so does this.

Only the configuration files are read, never `~/.aws/credentials`.

Under `--federated` the environment is left as the run gives it, and `federated`
refuses unless it holds a federated identity and nothing long-lived: a machine has
no GitHub token to request, so the argument cannot stand in for a profile there.
"""

import configparser
from pathlib import Path

from wizard.validity import Refused

NO_DEFAULTS = "\0"  # a default section no file can name, so `DEFAULT` is an ordinary one
AWS = ("AWS_CONFIG_FILE", ".aws/config")
DATABRICKS = ("DATABRICKS_CONFIG_FILE", ".databrickscfg")
ACCOUNT_CONSOLE = "https://accounts."

# Each provider: its argument, the variable the providers and SDKs read it from, the
# profile file it is listed from, and its name in a refusal.
PROVIDERS = {
    "aws": ("--aws-profile", "AWS_PROFILE", AWS, "AWS"),
    "databricks": ("--databricks-profile", "DATABRICKS_CONFIG_PROFILE", DATABRICKS, "Databricks"),
}
BOTH = ("aws", "databricks")

# What selects or overrides an identity, removed before the named profiles are set
# The configuration files' locations and the region stay.
REMOVED = ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
           "AWS_SESSION_TOKEN", "AWS_ROLE_ARN", "AWS_ROLE_SESSION_NAME",
           "AWS_WEB_IDENTITY_TOKEN_FILE")
REMOVED_PREFIXES = ("AWS_CONTAINER_", "DATABRICKS_")
KEPT = ("DATABRICKS_CONFIG_FILE",)

FEDERATED = "--federated"
# What a pipeline's run must not hold under `--federated`: a profile, or a
# credential that does not expire.
LONG_LIVED = ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "DATABRICKS_CONFIG_PROFILE",
              "DATABRICKS_TOKEN", "DATABRICKS_CLIENT_SECRET", "DATABRICKS_PASSWORD")


def add_arguments(parser, providers=BOTH, federated=False):
    """`--aws-profile` and `--databricks-profile`, for the providers a command takes, and
    `--federated` where the command runs in a pipeline. Not `required`: a missing one is
    `require`'s refusal, exit `1`, not a usage error."""
    for provider in providers:
        flag, _, _, name = PROVIDERS[provider]
        parser.add_argument(flag, metavar="NAME",
                            help=f"the {name} profile to act as; a profile, never a credential")
    if federated:
        parser.add_argument(FEDERATED, action="store_true",
                            help="take the pipeline run's federated identity in place of both "
                                 "profiles")


def act_as(environ, aws=None, databricks=None):
    """Rewrite `environ` in place so the named profiles are its only identity, and
    return it. A profile not given leaves its variable unset, for `require` to refuse."""
    for name in [name for name in environ if removed(name)]:
        del environ[name]
    for provider, given in (("aws", aws), ("databricks", databricks)):
        if given:
            environ[PROVIDERS[provider][1]] = given
    return environ


def removed(name):
    return name not in KEPT and (name in REMOVED or name.startswith(REMOVED_PREFIXES))


def require(environ, home, needed):
    """Refuse, listing what is configured, unless each provider in `needed` has its
    profile named. Reads `environ` as `act_as` left it, so only the arguments count."""
    missing = [provider for provider in needed if not environ.get(PROVIDERS[provider][1])]
    if missing:
        raise Refused("\n".join(_missing(provider, environ, home)
                                       for provider in missing))


def _missing(provider, environ, home):
    flag, _, kind, name = PROVIDERS[provider]
    path, shown = location(environ, home, kind)
    found = sections(path)
    if provider == "aws":
        listed = aws_profiles(found)
    else:
        listed = [f"{profile} ({where})" for profile, where in databricks_profiles(found)]
    lines = [f"no {name} profile is named: give {flag} NAME"]
    lines += ([f"  profiles in {shown}:"] + [f"    - {item}" for item in listed] if listed
              else [f"  no profiles in {shown}"])
    return "\n".join(lines)


def federated(environ):
    """Refuse, naming each condition that fails, unless `environ` holds a pipeline run's
    federated identity and nothing long-lived. Reads whether variables are
    set, and the values of `DATABRICKS_AUTH_TYPE` and `DATABRICKS_CLIENT_ID` only."""
    failing = []
    token = ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not all(environ.get(name) for name in token):
        failing.append(f"the run cannot get GitHub's token: {' and '.join(token)} must be set "
                       "(the job needs `id-token: write`)")
    if (environ.get("DATABRICKS_AUTH_TYPE") != "github-oidc"
            or not environ.get("DATABRICKS_CLIENT_ID")):
        failing.append("Databricks is not federated: DATABRICKS_AUTH_TYPE must be github-oidc "
                       "and DATABRICKS_CLIENT_ID set")
    session = environ.get("AWS_ACCESS_KEY_ID") and environ.get("AWS_SESSION_TOKEN")
    web = environ.get("AWS_WEB_IDENTITY_TOKEN_FILE") and environ.get("AWS_ROLE_ARN")
    if not (session or web):
        failing.append("AWS holds no temporary credential: AWS_ACCESS_KEY_ID with "
                       "AWS_SESSION_TOKEN, or AWS_WEB_IDENTITY_TOKEN_FILE with AWS_ROLE_ARN")
    held = [name for name in LONG_LIVED if name in environ]
    if held:
        failing.append(f"a profile or long-lived credential is set: {', '.join(held)}")
    if failing:
        raise Refused("--federated takes the pipeline run's federated identity, and "
                             "this environment does not hold one:\n"
                             + "\n".join(f"  {line}" for line in failing))


def carried(environ):
    """The profile arguments a next line carries: each this run was given.
    A run is given only what its command takes, and every next command it names takes
    at least that much, so nothing here depends on which command comes next."""
    args = []
    for flag, variable, _, _ in PROVIDERS.values():
        if environ.get(variable):
            args += [flag, environ[variable]]
    return args


def location(environ, home, kind):
    """`(path, shown)` of a profile file: where its variable says, else `~/<default>`."""
    variable, default = kind
    if environ.get(variable):
        return Path(environ[variable]), environ[variable]
    return Path(home) / default, f"~/{default}"


def sections(path):
    """`{section: its own keys}`, in file order; `{}` where the file cannot be read."""
    parser = configparser.ConfigParser(default_section=NO_DEFAULTS, interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return {}
    return {name: dict(parser[name]) for name in parser.sections()}


def aws_section(profile):
    """The section an AWS profile is written in, as the AWS CLI reads it."""
    return profile if profile == "default" else f"profile {profile}"


def aws_profiles(found):
    """The AWS profile names among `sections()`: `[default]` and `[profile <name>]`."""
    return [name if name == "default" else name[len("profile "):]
            for name in found if name == "default" or name.startswith("profile ")]


def databricks_profiles(found):
    """`(name, reach)` for each Databricks profile: the account console, a workspace, or no host."""
    return [(name, reach(keys.get("host"))) for name, keys in found.items()
            if name != "__settings__"]


def reach(host):
    if not host:
        return "no host"
    return "account console" if host.startswith(ACCOUNT_CONSOLE) else "workspace"
