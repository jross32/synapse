"""A facade satisfies a contract by re-exporting, and the checker has to see that.

Measured: splitting `storage` into three focused modules made all three pass on all four
runs - 12 for 12, against 0/4 for the nine-function monolith. The facade over them was then
rejected with "storage.py does not define `create_user(email, password_hash)`. It defines:
['init_db']", because `public_interface` read `def` statements and a facade has almost none.

The split was the best result of the sweep and the contract checker was the only thing
standing in front of it.
"""

from __future__ import annotations

from synapse_daemon.scaffold.contracts import (
    FunctionSpec,
    ModuleContract,
    check_contract,
    public_interface,
)

FACADE = '''"""Re-exports three modules."""
from store_records import add_record, delete_record, init_records, list_records
from store_users import create_user, get_user_by_email, init_users

__all__ = ["init_db", "create_user"]


def init_db():
    init_users()
    init_records()
'''

WANTED = ModuleContract(module="storage", functions=[
    FunctionSpec(name="init_db"),
    FunctionSpec(name="create_user", args=["email", "password_hash"]),
    FunctionSpec(name="get_user_by_email", args=["email"]),
    FunctionSpec(name="add_record", args=["user_id", "title", "amount", "date"]),
    FunctionSpec(name="list_records", args=["user_id"]),
    FunctionSpec(name="delete_record", args=["record_id", "user_id"]),
])


def test_reexported_names_count_as_exposed(tmp_path):
    path = tmp_path / "storage.py"
    path.write_text(FACADE, encoding="utf-8")

    found = {f.name for f in public_interface(path).functions}
    assert "create_user" in found, (
        "a re-exported name is on the module exactly as a def would be, and a facade is "
        "the sane way to assemble split pieces")
    assert "init_db" in found

    assert check_contract(path, WANTED) == [], (
        "the facade satisfies its contract and was rejected anyway")


def test_a_name_that_is_neither_defined_nor_imported_is_still_caught(tmp_path):
    """Widening the check must not blunt it."""
    path = tmp_path / "storage.py"
    path.write_text(FACADE, encoding="utf-8")

    wanted = ModuleContract(module="storage", functions=[
        FunctionSpec(name="delete_session", args=["token"])])
    problems = check_contract(path, wanted)
    assert problems and "delete_session" in problems[0], problems


def test_a_wrong_signature_in_a_real_definition_is_still_caught(tmp_path):
    """Only re-exports skip the argument comparison; a local def is checked as before."""
    path = tmp_path / "storage.py"
    path.write_text("def create_user(email, password):\n    return 1\n", encoding="utf-8")

    problems = check_contract(path, ModuleContract(module="storage", functions=[
        FunctionSpec(name="create_user", args=["email", "password_hash"])]))
    assert problems and "password_hash" in problems[0], problems


def test_underscored_and_star_imports_are_not_treated_as_interface(tmp_path):
    path = tmp_path / "storage.py"
    path.write_text("from helpers import *\nfrom helpers import _secret, ok\n",
                    encoding="utf-8")
    found = {f.name for f in public_interface(path).functions}
    assert found == {"ok"}, f"star and underscored imports leaked into the interface: {found}"
