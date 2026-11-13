# databricks-wizard

https://github.com/user-attachments/assets/fa9cd3f8-fdab-41f8-bc70-7e833869768d

A Claude Code skill that walks a team through the architecture decisions for a Databricks lakehouse,
and writes the answers as a set of ADRs: the target state an estate is measured against.

Some decisions are the team's to make, and the skill asks them. Others follow a vendor
recommendation, and the skill states them, with the vendor's own words and the date they were
checked. The team accepts them, or opts out and says why. Everything is recorded: what was chosen,
what was declined, and the reasons.

## Workflows

- **`describe`** walks one module of decisions, one card at a time, and writes the ADR set into your
  ADR monorepo.
- **`validate`** checks a written ADR set, or the skill's own decision corpus. For a set, it also
  says which decisions have been added, changed or removed in the skill since the set was written.
- **`audit`** reads your live Databricks account and measures it against the platform set, however
  the account was built: Terraform, the UI or anything else. It asks which account to read, which
  of its workspaces are your estate and which environment each holds, and keeps that answer in
  `audit/live.yaml` for the next audit. It only reads, with your own Databricks and AWS profiles.

## Install

You need [uv](https://docs.astral.sh/uv/) on your `PATH`.

### As a Claude Code plugin

In Claude Code:

```
/plugin install databricks-wizard --marketplace Cloudamite/databricks-wizard
```

On a Claude Code older than 2.1.275, add the marketplace first, then install from it:

```
/plugin marketplace add Cloudamite/databricks-wizard
/plugin install databricks-wizard@databricks-wizard
```

The plugin is the last released version. The skill is then `/databricks-wizard:databricks-wizard`;
its Python environment is built on first use. Claude Code offers each new release when it updates
its plugins.

### From a clone

You also need `python3`. A clone holds `main`, which may be ahead of the last release. Clone this
repository and run its installer:

```sh
git clone git@github.com:Cloudamite/databricks-wizard.git
python3 databricks-wizard/install.py
```

It asks where to install the skill. Press Enter for `~/.claude/skills/databricks-wizard`, where
Claude Code finds it in every project, or give a project's `.claude/skills/databricks-wizard`. It
copies the skill there and builds the skill's own Python environment with uv. Nothing is installed
into your own Python.

To upgrade, pull the clone and run the installer again. It asks before replacing the folder, and
replaces it whole.

## Use

Installed as a plugin, the commands below start `/databricks-wizard:databricks-wizard` instead of
`/databricks-wizard`.

Both teams keep their sets in one ADR monorepo. In Claude Code, run `/databricks-wizard describe` there and
name the module to walk:

- the platform team walks `platform-core`, and its set is written to `platform/`;
- a product team walks `product-core` and names its product, and its set is written to
  `products/<name>/`. The platform set must be written first: a product walk starts from it.

Each folder holds a machine-readable `adr-set.yaml` and one Markdown ADR per decision.

A set is written once. To change it, delete it and walk again.

To audit the live account, run `/databricks-wizard audit` in the same monorepo once the platform set
is written. You need a Databricks profile that reaches your account console (`databricks auth login
--host <account console URL> --account-id <account id>`), as a principal that can read the account,
its workspaces and their metastores. To include bucket versioning, you also need an AWS profile that
can read the S3 buckets behind the storage roots. The audit writes its files to `audit/`.

## Audit without Claude Code

The audit needs no language model. It is one command you can run yourself.

You need [uv](https://docs.astral.sh/uv/), a written platform set (`platform/adr-set.yaml` in your
ADR monorepo), and the profiles listed under [Use](#use). Clone the last release:

```sh
git clone --branch release git@github.com:Cloudamite/databricks-wizard.git
```

**Once: say which workspaces are your estate.** The audit reads this from `audit/live.yaml` in your
monorepo. Run the audit command below before the file exists. It writes `audit/live.yaml` for you to
fill in, then stops without auditing. The file has an entry for each environment your platform set
records, and lists your account's workspaces in a comment:

```yaml
schema_version: 1
name: platform
# The account's workspaces:
#   acme-dev
#   acme-prod
#   acme-sandbox
#   other-team
workspaces:
  - name:  # <fill here the name of the workspace for dev>
    environment: dev
  - name:  # <fill here the name of the workspace for prod>
    environment: prod
```

Fill in each `name` from the list. Add an entry with only a `name` for each other workspace of your
estate that holds no environment:

```yaml
workspaces:
  - name: acme-dev
    environment: dev
  - name: acme-prod
    environment: prod
  - name: acme-sandbox
```

If your platform set shares one workspace between environments, the file has a single entry with no
`environment` instead. If the command cannot list your workspaces, the comment says why, and you
type the names yourself. The audit refuses the file until every `name` is filled in.

Commit `audit/live.yaml`. Every later audit reuses it.

**Each time: run the audit** from the monorepo:

```sh
uv run --project <clone>/scripts --locked --group audit <clone>/scripts/audit_live.py \
    --databricks-profile <profile> --aws-profile <profile>
```

If you cannot read the buckets behind the storage roots (Databricks manages them, or they are in
another AWS account), pass `--no-storage` in place of `--aws-profile`. Bucket versioning is then
reported as unevaluated.

The command reads the account with read calls only, then measures what it read. It prints a report
for people to read and writes the structured one to `audit/audit.json`. What it read is kept in
`audit/snapshot.json`.

| Exit | Meaning |
|---|---|
| `0` | no deviations |
| `1` | deviations found |
| `2` | could not run, and nothing was measured. The message says why |

It refuses before reading the account if `audit/live.yaml` is malformed, or if a workspace's
environment is not one your platform set records. A workspace name the account does not have stops
the read, naming it. A workspace you left out is listed in the report, but not measured.

A report of 0 deviations does not mean the account conforms. Read all four counts: deviations,
unevaluated, conformant and not enforced. A high unevaluated count means little was measured. The
report also names the principal it read as. Anything that principal cannot see is missing from the
snapshot, so it is not measured.

## What it decides

- **`platform-core`**, the lakehouse foundations: how workspaces and catalogs are isolated, which
  naming level carries the environment, how the medallion layers map to schemas, and what the
  infrastructure-as-code layer manages.
- **`product-core`**, how a product team deploys and promotes its bundle: the identity its jobs run
  as, how development deployments are kept apart, which branches environments deploy from, what is
  promoted between environments, and how a full refresh is run. The platform's answers remove options here, and the environments it named
  are not asked again.

## License

MIT: see [LICENSE](LICENSE). The software is provided as is, without warranty; see
[LIABILITY.md](LIABILITY.md) for the full liability disclaimer.
