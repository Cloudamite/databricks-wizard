---
name: databricks-wizard
description: 'Establish a Databricks target state as an ADR set in a shared ADR monorepo, by walking a platform team through the lakehouse-foundations decisions or a product team through how it deploys and promotes its bundle. Records what the team chose, what they declined and why, validates a corpus or a written set, and audits a live Databricks account against the platform set, however the account was built.'
argument-hint: 'describe | validate | audit'
author: Mikko Alutoin
user-invocable: true
---

# databricks-wizard

Walks a team through one module of decisions and writes the result as an ADR set in the ADR
monorepo both teams share. A data platform team walks `platform-core`, the lakehouse foundations,
and its set lands in `platform/`. A data product team walks `product-core`, how it deploys and
promotes its bundle, and its set lands in `products/<name>/`. A product walk starts from the
platform set: the platform's answers remove options, and its names are not asked again. The set is
the target state: other tools measure an estate against it.

The engine is complete and tested. **You are its renderer.** The walk hands you a card as JSON and
you turn it into something the team can read and answer. Nothing else renders — so the rules below
are the presentation contract, not suggestions.

## Workflows

| Workflow | What it does |
|---|---|
| `describe` | Walks the decision surface and writes the ADR set |
| `validate` | Checks a corpus or a written ADR set |
| `audit` | Reads the live Databricks account and measures it against the platform set |

**Invoked with no argument, ask which workflow is wanted before running anything.** List the three
to the team as a numbered list, one line each saying what that workflow does, and start nothing
until they name one.

Do not default to `describe`. A team that named no workflow has not asked for a walk, and `describe`
writes to their repository — and it refuses to run twice, so a walk started by a default is a walk
they cannot undo without deleting the set it wrote.

Invoked with a workflow named, run that one and do not ask.

**Every script runs through uv**, exactly as each command below spells it:
`uv run --project <skill>/scripts --locked <skill>/scripts/<script>.py …`. uv supplies the Python
and the locked packages the skill was tested with. If `uv` is not found, stop and tell the team to
install it (https://docs.astral.sh/uv/). Do not fall back to `python3`, and do not `pip install`
anything: installing into the team's interpreter is what the skill's own environment exists to
avoid.

## The `describe` workflow — establishing a target state

The run is a cursor, not a questionnaire: each answer can remove options from later entries or
remove an entry outright, so there is no list of questions to show in advance. Drive it one card at
a time.

`<repo>` is the root of the team's ADR monorepo: the repository both teams keep their sets in.
It is the folder Claude Code was started in. Do not ask for it: name it in one line when the walk
starts, so the team can say if their monorepo is somewhere else, and use another folder only when
they do.

**First, the module.** List what the skill ships and ask which one the walk is for:

```bash
uv run --project <skill>/scripts --locked <skill>/scripts/session.py modules --corpus <skill>/corpus
```

It prints each module with its type and summary. Show them as a numbered list, one line each, and
start nothing until the team names one. Do not pick one for them, and do not walk one by default.
For a `product` module, also ask for the product's name: lowercase letters and digits, in groups
joined by single hyphens, such as `orders` or `customer-360`. It becomes the set's folder. Do not
invent or normalise a name; pass what the team gave, and if `start` refuses it, ask again.

```bash
uv run --project <skill>/scripts --locked <skill>/scripts/session.py start --corpus <skill>/corpus --module <module> [--product <name>] --repository <repo>
uv run --project <skill>/scripts --locked <skill>/scripts/session.py answer --repository <repo> --key <key> [--rationale "..."]
uv run --project <skill>/scripts --locked <skill>/scripts/session.py write  --repository <repo>
```

`start` validates the module **and checks the repository** before it returns anything, then
prints the first card. A defective corpus, a folder that already holds a set with nothing new to
ask, and — for a product module — a missing or invalid platform set in `<repo>/platform/` are all
exit `2`, and none is overridable.

**A set the skill has moved past is walked up.** When the folder already holds a set and the module
this skill ships has entries the set does not record, `start` appends: its response carries
`append`, and the cards are only the new entries. Before the first card, tell the team which
corpus version the set was written from (`recorded_version`) and which this skill ships
(`shipped_version`), name the entries it will be asked (`new`), and name any `changed` or
`removed`, saying they stay as recorded, since changing a recorded ADR is amendment. For a product
set, `builds_on` says the set will name the platform set as it is now. The recorded ADRs are written
again unchanged and the new ones are numbered after them. Do not ask whether to proceed: appending
is the only thing `start` does with an existing set, and nothing is written until `write`. Where
`start` refuses an append instead, report its stderr: it names every reason. A product team whose monorepo has no platform set yet needs the platform team to
walk `platform-core` first; say so.

A product walk is pinned to the platform set it started from, and an append to the set it adds
to. If that set changes before the walk is written, every later command stops with exit `2` and says
so: report it, and offer to start again with `start --restart`. Answers already given were chosen
from options that may have changed.

A card may show a removed option or a given name attributed to an ADR written like
`platform-core/ADR-003`: that is an ADR of the platform set, not of the set being written.
`answer` records an answer and prints the next card. When a response has `"done": true`, every
entry is settled — call `write`. Also available: `card` (re-print the card in hand, to resume a run
from a previous session) and `abandon` (discard the run; the repository is left as it was).

**A resumed walk shows its card again, in full.** Whenever the card in hand was not rendered in
this turn — a new session, `describe` invoked while a run is open, the team coming back after
closing the widget — run `card` and render what it prints in full, ending with the same last line.
Never point to an earlier rendering, such as "the card above": it may have scrolled away, been
summarised, or belong to another session, and a team that cannot see the card has not been shown
it.

Exit codes, and what each means for you:

| Code | Meaning | What to do |
|---|---|---|
| `0` | fine | render the card, or report the write |
| `1` | the answer was refused | **re-prompt.** The run is unchanged and the card is still in hand |
| `2` | cannot run | **stop.** Report what stderr says; nothing was written |

A refusal is not a failure of the run. `stdout` still carries the card, and `stderr` says why the
answer was not taken — usually a key that is not offered, or an opt-out with no rationale.

`write` prints the closing report: a card whose `kind` is `report`, read back off the set as written.
Render all of it — `entries` and `paths`, the `chosen` and `prescribed` counts, every
`declined` entry with the rationale the team gave, every `left_open` entry with its
`unconstrained` sentence (an answer that enforces nothing), every `inapplicable` entry with the entry
that made it so, and every `unattached_advice` entry in full with its citation and `no_rule_notice`
beneath it. `no_rule_notice` is always present and belongs to the unattached advice: where there is
none, there is nothing for it to qualify, so do not show it. After an append, every count and list
covers only the ADRs it added; say also how many recorded ADRs were left as they were
(`left_as_recorded`). The report is not a record and is not written anywhere; a halted or abandoned
run has none.

## Rendering a card

**Walk `disclosure` in the order it gives, and render only the parts it names.** It is an ordered
tuple precisely so that sequence is data rather than something a renderer decides: a prescription
must open with the target state and must say the decision is permanent *before* the choice. Do not
reorder it, do not add a part it omits, and do not skip a part it names. A part absent from the
tuple is a part the entry does not have.

The parts, and what each means:

| Part | Render |
|---|---|
| `question` | the decision being put to the team (decisions) |
| `target_state` | the state the product asserts (prescriptions) |
| `why` | the reasoning behind that assertion |
| `vendor` | see below — **verbatim** |
| `check` | `summary` as what will be checked, plus `enforceability`, plus `unevaluable_when` if set, plus — where `scope` is `estate` — that it is checked across the whole estate and needs a plan for every declared root |
| `write_once` | a plain statement that this cannot be changed later — see below |
| `options` | each `label`, its `cost`, what it compiles to (`check.summary`), and — rendered with that option — its `enforceability`, its `unevaluable_when` and its `parameters`. `check.scope` is the exception: see below. An option with no `check` carries `unconstrained` instead: render it as *checks nothing*, followed by that sentence, so the team reads before choosing that this answer enforces nothing |
| `not_offered` | options removed by an earlier answer, with their provenance — never hide these |
| `advice` | guidance shown and never asked |
| `responses` | how the team may respond — `choose`, or `accept` / `opt-out` |

### The vendor's position is quoted, never paraphrased

Show `vendor.quote` **verbatim**, with `vendor.source` and the date in `vendor.checked`. A team
reading a two-year-old date knows what to do with it; a team reading your summary of a quote does
not know what the vendor actually said. `vendor.verified_against` names the provider release the
claim was checked against — show it.

`strength` may be `silent`. That is a position and is shown as one: the vendor has no published
guidance here, which is different from the product having failed to look.

Advice carries its **own** citation. Never show a card's `vendor` under a piece of advice, or the
reverse — one vendor's words under another entry's source is worse than no source at all.

### The write-once notice comes before the choice

This version cannot amend a target state. `write_once` in the disclosure is where the team must be
told that, and it sits *before* `options` for a reason: a team that learns the decision was
permanent after making it was not given a choice, it was given a form.

### Show what was taken away

`not_offered` names options the team cannot choose and, in `because`, the answer that removed them.
`because.entry` is the entry responsible and `because.answer` the answer given — when `answer` is
`null` the removal cascaded, and `because.entry` names the next link in the chain.

Render these. Hiding a pruned option makes the wizard look arbitrary; showing it is how a team
learns the platform rather than merely obeying the tool.

### A caveat belongs to the state that declares it

`check.enforceability` and `check.unevaluable_when` tell the team what the analyzer will and will
not be able to see. Disclose both at choosing time. A team that learns an entry was weakly
enforceable from a silent UNEVALUATED three weeks later concludes the tool is broken.

**Where they render is part of the disclosure.** A prescription declares its caveat on the card's own
`check`, so it renders with the target state. A decision declares one per option, so each renders
inside the block of the option it qualifies — a team reading a condition has to be able to see which
state it conditions. There is no part of the card that collects them, and you do not make one.

**Never state a caveat across more than one option.** Where several options on offer declare the same
condition, it is rendered against each of them, in full, however repetitive that looks. A sentence
like *"and all three are unevaluable when the estate declares no catalogs"* is not a summary of the
card — it is a claim the card does not carry, in words no corpus author wrote, and a team cannot tell
it from the ones who did. The rule is the vendor-quote rule one level up: **transcribe against the
item, never compose across items.**

**`check.scope` is the one fact that hoists.** Where it is `estate`, the rule is checked across the
whole estate and can only be evaluated when the analyzer is given a plan for every declared root —
a condition on the team's pipeline, not on their architecture, and worth saying before the answer
rather than as a non-result afterwards. Where `scope` is `root`, say nothing: it is the ordinary
reading, and remarking on it on every card turns disclosure into noise.

Say it **once, above the states, when every state on offer is `estate`-scoped**, in words that say it
covers all of them — the team's obligation is the same whichever they pick, so it is a fact about the
decision. Where the states differ, say it on each `estate` state and hoist nothing: three of the six
decisions in the shipped corpus mix an `estate` state with a `root` one, and a hoisted line that is
not true of every state is the misattribution the rule above forbids. Recompute it from the card
every time; never carry it over from the last one.

### A parameter is asked once

Some states cannot be measured without names only the team can give — its environments, its
medallion layers. Such an option carries `parameters`, each with a `name` and the `question` to put.
Render the question inside that option's block, and when the team chooses it, ask for the values and
pass them as `--parameters '{"environments": ["dev", "qa", "prod"]}'`, in the order the team gave
them: the order is part of the answer, and for environments the last is production.

A parameter an earlier answer already supplied arrives **given**: `given` holds the values and
`given_by` the answer that supplied them. Show them against the option — *environments: dev, qa,
prod, given by your answer to DEC-001a* — and **do not ask again and do not pass them again**. A
second value is a second record of one fact, and the run refuses it (exit `1`). If the team wants
different values, that is a different answer to the card that asked.

### Advice is shown and never asked

An `advice` card, and advice attached to another card, is guidance nobody has yet found a way to
check. It yields no rule and never becomes an ADR. `no_rule_because` says why there is no check —
show it, so advice reads as guidance awaiting a fingerprint rather than guidance the product
declined to enforce. An advice card of its own has no `answer_keys`; advance it with
`answer` and no `--key`.

### Answering

`answer_keys` is what the run accepts. `options` is what the team chooses among. **They differ** —
a prescription's `declined` is an answer but not a state on offer, and a single-state prescription
has two answers and nothing to select between. Offer the team `answer_keys`.

**Opting out costs a rationale; accepting does not.** That asymmetry is deliberate: declining is the
act that leaves no reasoning behind. If the team declines, ask why and pass it as `--rationale`.
An opt-out with no rationale is refused (exit `1`) — re-prompt rather than inventing one.

`corpus_entry` is the entry's stable corpus id and is **never** an ADR number. Numbers are assigned
when the set is written. Do not show the team an ADR number during the walk; there isn't one yet.

`remaining_estimate` is an estimate and should be named as one. Later answers can prune, so the
count may fall by more than one between cards. There is no honest total.

### The selection is a widget; the disclosure is not

Render the card as prose, in `disclosure` order, in full, and **end your turn there**. Put the
choice to the team with `AskUserQuestion` only in your next turn, once they reply — one question,
one option per `answer_keys` entry, in the order the card gives them.

The card's last line, on its own, is:

> Type 'ok' to continue

The card gets a turn of its own because Claude Code does not show the text of a turn while that
turn's question is open: rendered in the same turn as the widget, the whole card shrinks to a line
and the team chooses from the widget alone. Ending the turn leaves the card in the conversation,
where the team reads it before anything asks them to choose.

When the reply is not a go-ahead, act on it instead of opening the widget:

- **It names an option** — its key or its label. Record that answer; the team has chosen.
- **It asks about the card.** Answer from the card, and open the widget only when they are ready.

The split is the point. A widget option is a label of a few words and a line of description; the
verbatim vendor quote, the write-once notice, `not_offered` and each option's own caveat do not fit
in one and must not be compressed until they do. **Anything that appears only in the widget was not
disclosed.** The widget collects an answer the team has already been given the means to make; it
never carries the reasoning.

Each option names its `answer_keys` key and glosses the cost, so a click is traceable back to what
the run records. Where the check summary fits in a line, include it; where it does not, it is
already in the prose above.

Three cases the widget does not cover:

- **An advice card** has no `answer_keys` and nothing to select. Show it and advance with `answer`
  and no `--key` — no widget.
- **An opt-out still costs a rationale.** The widget records that the team chose `declined`; it does
  not supply the why. Ask for that in the next turn as free text and pass it as `--rationale`.
  Never pre-fill it from the option's description — a rationale the team did not write is an
  invention, and the refusal at exit `1` exists to stop exactly that.
- **More than four `answer_keys`** exceeds what the widget accepts. Ask in prose instead. Today's
  corpus offers at most three, so this is a rule for a corpus that grows, not for this one.

## The `validate` workflow

The same validator a team runs as a CI stage, on a corpus or an emitted set:

```bash
uv run --project <skill>/scripts --locked <skill>/scripts/validate.py <skill>/corpus          # every module
uv run --project <skill>/scripts --locked <skill>/scripts/validate.py <repo>/platform/adr-set.yaml   # `adrs:` — an ADR set
```

A directory is a corpus — the corpus root checks every module, a module's directory that module
alone; a file is an ADR set when it carries the `adrs` key its schema requires.

**A valid set is also compared with the module this skill ships.** After `adr-set is valid`, the
output says the set is current, or lists the entries that are new (questions the set never
answered), changed since the team chose from them, or removed from the corpus. This never changes
the exit code. Relay it as it is: the set still measures as before, and walking a set up to a newer
corpus is not something this version can do. For a set written before entry digests, it can only
say that entries may have changed.
It also checks a live estate declaration, the file the `audit` workflow keeps its workspaces in:

```bash
uv run --project <skill>/scripts --locked <skill>/scripts/validate.py <repo>/audit/live.yaml   # `workspaces:`
```

Exit `0` valid, `1` invalid, `2` could not run. It makes no network request, invokes no language
model, and reads no clock — two runs over identical input give identical output.

## The `audit` workflow — measuring the live account

`audit` measures a team's live Databricks account against its platform set: what is actually
there, however it got there, including what was created in the UI. Terraform plays no part, so it
works on any estate, however it was built. It audits the **platform** estate only; a product team's
estate is not audited in this version.

`<repo>` is the ADR monorepo, as for `describe`: the folder Claude Code was started in. Name it in
one line when the audit starts. The audit measures `<repo>/platform/adr-set.yaml`. If there is no
platform set, stop: the platform team walks `platform-core` with `describe` first. Everything the
audit writes goes in `<repo>/audit/`:

| File | What it is | Kept |
|---|---|---|
| `audit/live.yaml` | the **live estate declaration**: which of the account's workspaces are the estate, and the environment each holds | reused by the next audit; worth committing |
| `audit/snapshot.json` | what the reader saw in the account | replaced each audit |
| `audit/audit.json` | the report | replaced each audit |

The snapshot holds no credential, but it names the team's workspaces, catalogs and schemas. Whether
to commit the snapshot and the report is the team's call.

The audit is three steps. The first two settle what to read and as whom; the third is one command,
`audit_live.py`, which reads the account with the team's credentials and then measures what it read,
from files only. A team without Claude runs the same command (the README says how).

### 1. Say which workspaces are the estate

**If `<repo>/audit/live.yaml` exists**, show it — each workspace and its environment — and ask
whether to reuse it or pick the workspaces again. Reuse is the usual answer: go to step 2, after
picking the Databricks profile as in 1a. Pick again only when they say so.

**Otherwise, or to pick again**, build it:

**1a. The Databricks profile.**

```bash
uv run --project <skill>/scripts --locked <skill>/scripts/live.py profiles
```

It prints `{"aws": [...], "databricks": [...]}` from the team's configuration files, without
reaching the network. The `databricks` list holds only the profiles that reach an account
console: a workspace profile cannot list an account. Show it as a numbered list and ask which to
read the account as. A read-only principal suits an audit better than a deploying one. Never take
a profile from the environment, and never ask for a token or a secret.

If the list is empty, the team has no account-level profile. Tell them to create one with the
Databricks CLI, `databricks auth login --host <account console URL> --account-id <account id>`,
and run `profiles` again. Do not go on without one.

**1b. The account's workspaces.** Say first that this reads the account the profile reaches, with
read calls only.

```bash
uv run --project <skill>/scripts --locked --group audit <skill>/scripts/live.py workspaces --databricks-profile <profile>
```

It prints the account it reached (`host`, `account_id`) and each workspace's `name`, `region` and
`status`, sorted by name. Name the account in one line, so the team can say if it is the wrong one.
Exit `2` prints nothing on stdout: show stderr, which names what failed and the profile, and go
back to 1a. A profile that reaches a workspace, or names no account, is refused there.

**1c. Which are theirs, and which environment each holds.** Show the workspaces as a numbered list
and ask which are part of the estate. The account may hold other teams' workspaces; take only the
ones they name. Then, for each one picked, ask which environment it holds. The choices are the
environments the platform set records — the `environments` value under `parameters` in
`<repo>/platform/adr-set.yaml` — and *none*. Offer nothing else. Label every workspace that holds an
environment: without labels the audit cannot tell a production workspace from any other.

**1d. Write the declaration.**

```bash
uv run --project <skill>/scripts --locked <skill>/scripts/live.py declare \
    --set <repo>/platform/adr-set.yaml --out <repo>/audit/live.yaml \
    --workspace <name>=<environment> --workspace <name> ... [--replace]
```

One `--workspace` per workspace picked: `<name>=<environment>`, or `<name>` alone for *none*. Pass
`--replace` only when the team chose to pick again over an existing declaration. Exit `0` prints
the path written. Exit `2` writes nothing: show stderr. A label the set does not record is refused,
naming the ones it does. Two workspaces with one environment, or an environment with no workspace,
are written as given: they are for the audit to report, not for you to correct.

### 2. The AWS profile, or no storage

The reader also reads each S3 bucket behind the account's storage roots, for bucket versioning
(PRE-001). Ask which AWS profile to read them as, from the `aws` list `profiles` printed, numbered,
with one more choice at the end: **"I can't read the buckets"** — the storage is Databricks-managed,
or in another AWS account. Say what that choice costs before they pick it: bucket versioning is then
reported unevaluated until they audit again with a profile that reaches the buckets. Never pick it
for them, and never fall back to it after a failed read. The principal needs
`s3:GetBucketVersioning` and `s3:GetLifecycleConfiguration` on each bucket.

### 3. Read and measure the account

Say before running it that it reads the account and the buckets, as the two profiles, with read
calls only, and then measures what it read. Run it from `<repo>`:

```bash
cd <repo> && uv run --project <skill>/scripts --locked --group audit <skill>/scripts/audit_live.py \
    --databricks-profile <profile> (--aws-profile <profile> | --no-storage)
```

`--no-storage` only when the team picked "I can't read the buckets", and then no `--aws-profile`.
It reads `platform/adr-set.yaml` and `audit/live.yaml`, and writes `audit/snapshot.json` and
`audit/audit.json`.

| Code | Meaning | What to do |
|---|---|---|
| `0` | read and measured: no deviation | report the result |
| `1` | read and measured: deviations found — a measurement, not an error | report the result |
| `2` | could not run, and **nothing was measured** | **stop.** Show stderr |

Exit `2` comes before the read when the files are wrong: no declaration, a defective one, a
defective set, or a workspace labelled with an environment the set does not record — the label is
the team's to correct. It comes after the read starts when the account or a bucket could not be
read: stderr names every workspace or bucket not read, with the reason, and the profile used.
There is no partial snapshot. A declared workspace the account does not list usually means the
profile reaches another account; one it lists but cannot read means the principal lacks access.
Either way the remedy is the configuration, not the declaration. A bucket the AWS profile cannot
read is the team's to fix, or to answer with "I can't read the buckets" — theirs to choose.

### Reporting the result

The audit writes the structured report and prints a rendering written for a reader. **Prefer the
rendering to a summary of your own**, and quote its counts exactly.

**Never report the deviation count alone.** The rendering leads with four counts: deviations,
unevaluated, conformant and not enforced. *0 deviations* beside a high unevaluated count does not
mean the account conforms; it means little was measured. Say all four, and say what the unevaluated
ones are waiting on. The rendering groups them by cause:

| Cause | What it means | Who resolves it |
|---|---|---|
| `estate-side` | the account holds nothing the rule could measure | nobody, necessarily: it may resolve as the estate grows |
| `product-side` | the rule has no fingerprint for a cloud this account is on | a corpus maintainer |
| `installation-side` | this version cannot evaluate it — storage on Azure or GCP, for one | upgrading this skill |
| `coverage-side` | part of the account was not read — the buckets, after "I can't read the buckets" | the team, **today**: audit again with an AWS profile that reaches them |

The four are closed: do not invent a fifth or merge two.

- **Say where each finding is.** The rendering's *By place* section gives the account's, each
  workspace's and each metastore's counts. Name the place whenever you mention a finding.
- **Name the principal.** The rendering's `read as:` line says whose view this is. A catalog the
  principal cannot see is absent from the snapshot, so a short count can mean a short read, not a
  clean account.
- **An undeclared workspace is listed, not measured.** If one is the team's own, they add it by
  picking the workspaces again, and audit again.
- **Some rules can never be answered from an account, and the audit leaves them out.** An account
  records no destroy protection (DEC-006a), no grant authority (DEC-006b) and no record of which
  tool created a catalog (PRE-002), so the report does not mention them. If a team asks where they
  went, say plainly that the account does not hold this fact, and no upgrade will supply it.
- **The audit gives no build verdict.** Do not turn the report into a pass or a fail yourself.

## What this version cannot do

State these plainly if a team asks; do not imply otherwise.

- **A re-run adds only what is new, and cannot re-author.** A folder that already holds a set is
  walked up when the shipped module has entries the set does not record, and refused before the
  first card otherwise; a folder that holds anything else is refused too. The refusal is per folder:
  the platform set does not stop a product walk, and one product's set does not stop another's. Do
  not check for the set yourself and do not ask the team whether to proceed — there is no flag that
  proceeds, because re-authoring is unbuilt and a second set written beside the first is worse than
  a refusal. Report what `start` put on stderr: it names the path, says whether the set is current
  or what moved since it was written, and says what deleting the set would cost.
- **Rules carry a literal `{adr}`, by design.** A rule's `failure_message` is a string the analyzer
  emits at report time, not prose the team reads in the set, and both its placeholders — `{catalog}`
  and `{adr}` — are resolved together by the rule compiler. The written document records
  the rule as authored. Say so if a team asks; it is not an unfinished edge.
- **No amendment.** The target state is write-once: a newer corpus adds ADRs to a set, and never
  changes a recorded one. A team that cannot comply opts out with a rationale; it cannot record the
  state it holds instead.
- **The audit reads one account, as one principal, and stops at the report.** It sees only what
  that principal can see. It records no exceptions, gives no build verdict, and does not run on a
  schedule. DEC-006a, DEC-006b and PRE-002 cannot be answered from an account at all. Of the
  storage behind the account, it reads S3 only. It audits the platform estate only: a product
  team's estate is not audited.
- **Module 1 only** — lakehouse foundations. Not ingestion, not the medallion pipeline's internals,
  not delivery or quality.

## How it is put together

The card/renderer seam that makes you the renderer is argued in `scripts/wizard/card.py`, and what
the renderer on your side of that seam owes the card is § Rendering a card above. The corpus is data,
not code: a maintainer adds an entry by writing YAML, and `validate.py` is what tells them it is
well-formed.
