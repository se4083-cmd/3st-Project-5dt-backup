import os

import pytest

from scripts.azure_migrate import blocking_locks, canonical_constraint, crypt


def test_varchar_array_deparse_keeps_exact_constraint_semantics():
    old = "CHECK ((x)::text = ANY ((ARRAY['A'::character varying, 'B'::character varying])::text[]))"
    restored = (
        "CHECK ((x)::text = ANY (ARRAY[('A'::character varying)::text, ('B'::character varying)::text]))"
    )
    assert canonical_constraint(old) == canonical_constraint(restored)
    for changed in [old.replace("'B'", "'C'"), old.replace("(x)", "(y)"), old + " NOT VALID"]:
        assert canonical_constraint(old) != canonical_constraint(changed)


@pytest.mark.parametrize(
    "definition",
    [
        "CHECK (x = ANY ((ARRAY['AB'::character varying(1)])::text[]))",
        "CHECK (x = ANY ((ARRAY[variable::character varying])::text[]))",
        "FOREIGN KEY (customer_id) REFERENCES customers(customer_id)",
    ],
)
def test_no_broad_sql_normalization(definition):
    assert canonical_constraint(definition) == definition


def test_shared_and_direct_locks_block_only_matching_resources():
    group = "/subscriptions/example/resourceGroups/5dt-final-team1"
    api = group + "/providers/Microsoft.Web/sites/old-a"
    suffix = "/providers/Microsoft.Authorization/locks/protect"
    shared = {"id": group + suffix, "level": "CanNotDelete"}
    direct = {"id": api + suffix, "level": "CanNotDelete"}
    other = {
        "id": group + "/providers/Microsoft.Storage/storageAccounts/team" + suffix,
        "level": "CanNotDelete",
    }
    assert blocking_locks([shared, direct, other], [api]) == [shared, direct]


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI backup test")
def test_private_backup_encryption_roundtrip():
    value = b"synthetic backup verification bytes"
    encrypted = crypt(value)
    assert encrypted != value
    assert crypt(encrypted, decrypt=True) == value
