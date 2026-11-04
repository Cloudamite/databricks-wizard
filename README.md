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
