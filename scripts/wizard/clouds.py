"""Which clouds an estate is on, read from its plans.

The cloud set is a **set**: an estate with an Azure Databricks workspace and an
AWS data-lake bucket is a real configuration, not a malformed one. It is derived
from the supplied plans' provider configurations and from nothing else — not the
ADR set, not the corpus, not the declaration, not the environment, and no flag
overrides it.

This is the first stage that reads a plan and the first that **cannot refuse**.
A plan naming no cloud the product recognises yields the empty set and the
analysis continues: every rule then compiles into the case that can only be
UNEVALUATED, and the report says so once at the top rather than per rule. A plan
the product cannot measure is a finding, not an error.
"""

# The table, fixed and shipped. Exactly three providers map to a cloud; no ADR
# set, corpus entry or argument extends it, which is checkable by reading this
# one file.
#
# It is a sequence rather than a dict because it carries two facts: the mapping,
# and the order a detected set comes back in. Compiled rules need a
# stable cloud order within an ADR and cannot produce one from an unstable
# input, so the order is settled here once rather than sorted again downstream.
CLOUDS = (
    ("registry.terraform.io/hashicorp/aws", "aws"),
    ("registry.terraform.io/hashicorp/azurerm", "azure"),
    ("registry.terraform.io/hashicorp/google", "gcp"),
)

BY_SOURCE = dict(CLOUDS)


def detect(plans):
    """The clouds `plans` configure, in the table's order, each once.

    `plans` is an iterable of parsed Terraform plans. Recognition keys on the
    **registry source address**, never on a provider block's local name: the
    local name is the team's to choose and an aliased configuration carries a
    name they chose, so `aws`, `aws.west` and a block named `primary` all
    resolve to one cloud — and a block named `aws` whose source is
    `hashicorp/random` resolves to none.
    """
    found = set()
    for plan in plans:
        for entry in _configured(plan):
            cloud = BY_SOURCE.get(entry.get("full_name"))
            if cloud is not None:
                found.add(cloud)

    return tuple(cloud for _, cloud in CLOUDS if cloud in found)


def _configured(plan):
    """Every `configuration.provider_config` entry of one plan.

    A plan carrying no `configuration` block and one carrying an empty
    `provider_config` are both plan shapes that exist, and both mean *no
    provider is configured here* rather than *this plan is malformed* — so
    neither is reached for and raised on.

    Detection reads what the plan declares as **configured**, not what it
    changes: a configured provider counts whether or not the plan manages a
    resource through it. Counting only providers with
    resources would silently drop a cloud a team has set up and not yet used,
    where the honest answer is a cloud whose rules compile and report an
    estate-side non-result.
    """
    if not isinstance(plan, dict):
        return ()
    configuration = plan.get("configuration")
    if not isinstance(configuration, dict):
        return ()
    provider_config = configuration.get("provider_config")
    if not isinstance(provider_config, dict):
        return ()
    return [entry for entry in provider_config.values() if isinstance(entry, dict)]
