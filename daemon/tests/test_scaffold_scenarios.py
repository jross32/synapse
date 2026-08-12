"""The contract says the door is the right shape; the scenario walks through it.

Pinned from a real false pass. The first blueprint build reported three of four pieces as
passing. Two of the three were unusable:

* ``passwords.verify_password`` raised ``NameError: name 'hmac' is not defined`` on every
  call - the module's whole purpose, broken, graded a clean pass with zero repairs.
* ``storage.create_user`` returned ``None`` and ``get_user_by_email`` returned a bare row
  tuple that did not even include the password hash, so its only caller could neither open
  a session nor check a password.

Both matched their declared contract exactly. Signatures were never the thing that was
wrong. These tests exist so that stays fixed.

``pages`` was also reported as unusable at first, and that was a mistake worth keeping in
view: the check asserted the literal string ``"kit.css"`` appeared in the rendered HTML,
while ``page()`` inlines the stylesheet instead of linking it. A correctly built page
failed a checker that had only ever been tried against broken input. Hence
``test_scenario_passes_the_repaired_module`` below - every scenario here is exercised in
both directions, because a checker that rejects everything is as useless as one that
accepts everything, and is much more convincing.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from synapse_daemon.blueprints import CheckKind, Piece
from synapse_daemon.local_pipeline import run_pipeline

BLUEPRINT = (Path(__file__).resolve().parents[2] / "blueprints" / "webapp-auth-crud"
             / "blueprint.json")


def _run_async(coro):
    """pytest-asyncio is not assumed here; these cases only need a loop of their own."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _pieces() -> list:
    """The blueprint as a build sees it: placeholders resolved to the default vocabulary."""
    from synapse_daemon.blueprints import get_blueprint

    return get_blueprint("webapp-auth-crud").instantiate().pieces


def _scenario(name: str) -> str:
    return next(p.tests for p in _pieces() if p.name == name)


def _run_scenario(tmp_path: Path, module: str, source: str) -> tuple[bool, str]:
    (tmp_path / f"{module}.py").write_text(source, encoding="utf-8")
    test = tmp_path / f"_scenario_{module}.py"
    test.write_text(f"from {module} import *\n\n{_scenario(module)}\nprint('OK')\n",
                    encoding="utf-8")
    import subprocess
    import sys
    proc = subprocess.run([sys.executable, test.name], capture_output=True, text=True,
                          timeout=120, cwd=str(tmp_path))
    return proc.returncode == 0, (proc.stderr or proc.stdout)


# The exact module the local model shipped, reduced to the part that matters.
BROKEN_PASSWORDS = """
import hashlib
import secrets

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000)
    return f'pbkdf2_sha256$200000${salt.hex()}${digest.hex()}'

def verify_password(password: str, stored: str) -> bool:
    parts = stored.split('$')
    salt = bytes.fromhex(parts[2])
    expected = bytes.fromhex(parts[3])
    got = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000)
    return hmac.compare_digest(expected, got)
"""

FIXED_PASSWORDS = BROKEN_PASSWORDS.replace("import hashlib", "import hashlib\nimport hmac")


def test_scenario_catches_a_module_that_crashes_on_its_main_function(tmp_path):
    """`hmac` is never imported, so verify_password raises on every call."""
    ok, output = _run_scenario(tmp_path, "passwords", BROKEN_PASSWORDS)
    assert not ok, "the scenario passed a module whose verify_password cannot run"
    assert "hmac" in output


def test_scenario_passes_the_repaired_module(tmp_path):
    """A checker that fails everything is no better than one that passes everything."""
    ok, output = _run_scenario(tmp_path, "passwords", FIXED_PASSWORDS)
    assert ok, f"the scenario rejected a correct module:\n{output}"


UNSALTED_PASSWORDS = """
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, stored: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == stored
"""


def test_scenario_catches_an_unsalted_hash(tmp_path):
    """Runs, verifies correctly, and is still the wrong thing to ship."""
    ok, output = _run_scenario(tmp_path, "passwords", UNSALTED_PASSWORDS)
    assert not ok, "the scenario accepted an unsalted password hash"
    assert "unsalted" in output


STORAGE_STUB = """
import sqlite3

_DB = 'database.db'

def init_db():
    c = sqlite3.connect(_DB)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT '
              'UNIQUE, password_hash TEXT)')
    c.commit(); c.close()

def create_user(email, password_hash):
    c = sqlite3.connect(_DB)
    try:
        c.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)',
                  (email, password_hash))
        c.commit()
    finally:
        c.close()

def get_user_by_email(email):
    c = sqlite3.connect(_DB)
    row = c.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    c.close()
    return row

def create_session(user_id): return 'tok'
def user_id_for_token(token): return None
def delete_session(token): pass
def add_record(user_id, title, amount, date): pass
def list_records(user_id): return []
def delete_record(record_id, user_id): pass
"""


def test_scenario_catches_correct_signatures_with_unusable_returns(tmp_path):
    """Every signature matches the contract. Nothing the caller needs comes back."""
    from synapse_daemon.scaffold import contracts as contracts_mod

    (tmp_path / "storage.py").write_text(STORAGE_STUB, encoding="utf-8")
    spec = next(p for p in _pieces() if p.name == "storage").contract
    expected = contracts_mod.ModuleContract(
        module="storage",
        functions=[contracts_mod.FunctionSpec(name=f["name"], args=f.get("args", []))
                   for f in spec["functions"]])

    # The old gate is satisfied by this module...
    assert contracts_mod.check_contract(tmp_path / "storage.py", expected) == []

    # ...and the new one is not.
    ok, output = _run_scenario(tmp_path, "storage", STORAGE_STUB)
    assert not ok, "the scenario accepted a storage module its caller cannot use"
    assert "create_user must RETURN" in output


def test_runner_feeds_the_scenario_into_the_repair_loop(tmp_path):
    """The scenario has to run *during* the build, not as a post-mortem.

    Checked through the pipeline's own plumbing with a stub generator, so it verifies the
    wiring rather than a model's output.
    """
    piece = Piece(name="storage", spec="irrelevant", module="storage",
                  tests="assert False, 'scenario reached the loop'",
                  checks=[CheckKind.UNIT])

    seen: dict[str, str] = {}

    def fake_run(test_file: Path, cwd: Path) -> tuple[bool, str]:
        seen["test"] = test_file.read_text(encoding="utf-8")
        return True, ""

    import synapse_daemon.local_pipeline as lp

    original = lp.generate_code
    lp.generate_code = lambda spec, model="": "def noop():\n    pass\n"
    try:
        _run_async(run_pipeline("spec", workspace=tmp_path, path="storage.py",
                                max_repairs=0, runner=fake_run,
                                extra_test=piece.tests))
    finally:
        lp.generate_code = original

    assert "scenario reached the loop" in seen.get("test", ""), (
        "the blueprint's scenario never reached the test the pipeline runs, so a piece "
        "could pass the build while failing the only check that models its caller")


TRAILS = {"record": "trail", "records": "trails", "Record": "Trail", "Records": "Trails",
          "title_field": "name", "amount_field": "distance_km"}


def test_one_blueprint_builds_more_than_one_domain():
    """The recipe is a shape; the nouns are an argument to it."""
    from synapse_daemon.blueprints import get_blueprint

    generic = get_blueprint("webapp-auth-crud")
    trails = generic.instantiate(TRAILS)

    assert trails.entrypoint["flow"]["create"]["path"] == "/api/trails"
    assert "name" in trails.entrypoint["flow"]["create"]["body"]
    assert "distance_km" in trails.entrypoint["flow"]["create"]["body"]

    storage = next(p for p in trails.pieces if p.name == "storage")
    add = next(f for f in storage.contract["functions"] if f["name"] == "add_record")
    assert add["args"] == ["user_id", "name", "distance_km", "date"], (
        "the contract still names the generic fields, so the module and the flow that "
        "attacks it would disagree")
    assert '_rows[0]["name"]' in storage.tests, "the scenario was not rewritten with it"

    # Substitution has to be total. A placeholder left anywhere means one artefact is
    # speaking a different language from the rest, which is the whole failure mode.
    import json as _json
    assert "{{" not in _json.dumps(trails.model_dump()), "an unsubstituted placeholder"


def test_instantiating_with_nothing_keeps_the_default_vocabulary():
    from synapse_daemon.blueprints import get_blueprint

    default = get_blueprint("webapp-auth-crud").instantiate()
    assert default.entrypoint["flow"]["create"]["path"] == "/api/records"
    assert "title" in default.entrypoint["flow"]["create"]["body"]


def test_every_builtin_piece_declares_a_scenario():
    """`tests: ""` is legal, means "no independent check", and is silent about it.

    That combination is what shipped three unusable modules. `api` in particular carried no
    scenario at all while being the hardest piece and the only one to escalate on both
    builds - it was asked for the most with the least feedback. This keeps the gap from
    being reintroduced by writing a new blueprint.
    """
    from synapse_daemon.blueprints import load_catalog

    missing: list[str] = []
    for blueprint in load_catalog():
        if blueprint.draft:
            continue
        for piece in blueprint.instantiate().pieces:
            if not piece.tests.strip():
                missing.append(f"{blueprint.id}.{piece.name}")

    assert not missing, (
        "these pieces can pass a build without any check the model did not write "
        f"itself: {missing}")


def test_no_scenario_still_carries_its_placeholders():
    """A `{{records}}` left unsubstituted would make the scenario assert on literal text."""
    for piece in _pieces():
        assert "{{" not in piece.tests, (
            f"{piece.name}'s scenario still contains an unresolved placeholder, so it "
            f"would test a route that does not exist")


def test_summary_separates_passing_from_independently_verified():
    """"N pieces built" must never again be able to mean N unusable modules."""
    from synapse_daemon.scaffold.runner import BuildResult, PieceOutcome

    result = BuildResult(
        blueprint_id="webapp-auth-crud", workspace="/tmp",
        pieces=[PieceOutcome(name="passwords", passed=True, verified=True),
                PieceOutcome(name="storage", passed=True, verified=False),
                PieceOutcome(name="pages", passed=True, verified=False)])

    text = result.summary()
    assert "3/3 pieces built locally, 1 independently verified" in text
    assert "NOT independently verified: storage, pages" in text, (
        f"the summary hid which pieces had no independent check:\n{text}")


def test_a_piece_without_a_scenario_is_never_marked_verified(tmp_path):
    """`tests: ""` means unverified, not verified-by-default."""
    import synapse_daemon.local_pipeline as lp
    from synapse_daemon.blueprints import Blueprint, Piece
    from synapse_daemon.scaffold.runner import build_blueprint

    blueprint = Blueprint(id="t", name="t", summary="t",
                          pieces=[Piece(name="thing", spec="anything", module="thing")])

    def stub(spec: str, model: str = "") -> str:
        # The pipeline asks the same callable for the code and then for a test of it.
        if "Write a test for that code" in spec:
            return "from thing import *\n\nassert noop() is None\nprint('OK')\n"
        return "def noop():\n    pass\n"

    original = lp.generate_code
    lp.generate_code = stub
    try:
        result = _run_async(build_blueprint(blueprint, workspace=tmp_path, max_repairs=0))
    finally:
        lp.generate_code = original

    piece = result.pieces[0]
    assert piece.passed, "the stub should pass its own generated test"
    assert not piece.verified, (
        "a piece with no declared scenario was reported as independently verified")
    assert piece.checks["scenario"].startswith("not_run")


def test_declared_checks_the_runner_cannot_execute_are_reported(tmp_path):
    """A check nobody ran must say so. `checks={}` reads as "nothing to check"."""
    import synapse_daemon.local_pipeline as lp
    from synapse_daemon.blueprints import Blueprint, CheckKind, Piece
    from synapse_daemon.scaffold.runner import build_blueprint

    blueprint = Blueprint(
        id="t", name="t", summary="t",
        pieces=[Piece(name="thing", spec="anything", module="thing",
                      checks=[CheckKind.UNIT, CheckKind.WEB, CheckKind.HTTP])])

    def stub(spec: str, model: str = "") -> str:
        if "Write a test for that code" in spec:
            return "from thing import *\n\nassert noop() is None\nprint('OK')\n"
        return "def noop():\n    pass\n"

    original = lp.generate_code
    lp.generate_code = stub
    try:
        result = _run_async(build_blueprint(blueprint, workspace=tmp_path, max_repairs=0))
    finally:
        lp.generate_code = original

    checks = result.pieces[0].checks
    # `web` is deferred rather than unimplemented - a page can only be rendered once the
    # app is assembled - so it must say that, not claim it was never run and not vanish.
    assert checks.get("web", "").startswith("deferred"), (
        f"a declared web check vanished instead of reporting itself: {checks}")
    assert "assembled app" in checks["web"], checks["web"]
    assert checks.get("http", "").startswith("not_run"), checks


def test_the_pages_scenario_accepts_a_page_built_from_the_supplied_partials(tmp_path):
    """The correction, pinned: `page()` inlines the kit, it does not link `kit.css`.

    The first version of this scenario asserted the string "kit.css" appeared in the
    output, which condemned a page that had been built exactly as intended.
    """
    import shutil

    from synapse_daemon.scaffold.partials import KIT_DIR

    scaffold = Path(__file__).resolve().parents[1] / "synapse_daemon" / "scaffold"
    (tmp_path / "ui_kit").mkdir()
    shutil.copy(KIT_DIR / "kit.css", tmp_path / "ui_kit" / "kit.css")
    shutil.copy(scaffold / "partials.py", tmp_path / "scaffold_partials.py")

    (tmp_path / "pages.py").write_text(
        "from scaffold_partials import field, page\n\n\n"
        "def landing_page():\n    return page('T', '<div class=\"card\">hi</div>')\n\n\n"
        "def signup_page():\n    return page('S', "
        "field('email', 'Email address', kind='email', autocomplete='email')\n"
        "        + field('password', 'Password', kind='password', "
        "autocomplete='new-password'))\n\n\n"
        "def login_page():\n    return page('L', "
        "field('email', 'Email address', kind='email', autocomplete='email')\n"
        "        + field('password', 'Password', kind='password', "
        "autocomplete='current-password'))\n\n\n"
        "def dashboard_page():\n    return page('D', '<ul id=\"rows\"></ul>')\n",
        encoding="utf-8")

    scenario = next(p.tests for p in _pieces() if p.name == "pages")
    (tmp_path / "_s.py").write_text(f"from pages import *\n\n{scenario}\nprint('OK')\n",
                                    encoding="utf-8")

    import subprocess
    import sys
    proc = subprocess.run([sys.executable, "-B", "_s.py"], capture_output=True, text=True,
                          timeout=120, cwd=str(tmp_path))
    assert proc.returncode == 0, (
        f"a page built from the supplied partials was rejected:\n"
        f"{proc.stderr or proc.stdout}")


def test_the_piece_is_shown_the_contract_it_will_be_held_to(tmp_path):
    """Enforcing signatures that were never stated makes the model pay to discover them.

    Measured on two consecutive runs of the `storage` piece: repair 1 was always "init_db
    is missing" and repair 2 was always "create_user takes ['email', 'password'] but the
    contract requires ['email', 'password_hash']" - roughly twelve minutes of local compute
    spent learning a fact that costs a few tokens to state.
    """
    import synapse_daemon.local_pipeline as lp
    from synapse_daemon.blueprints import Blueprint, CheckKind, Piece
    from synapse_daemon.scaffold.runner import build_blueprint

    blueprint = Blueprint(
        id="t", name="t", summary="t",
        pieces=[Piece(name="store", spec="Write a store.", module="store",
                      checks=[CheckKind.UNIT, CheckKind.CONTRACT],
                      contract={"functions": [
                          {"name": "init_db", "args": []},
                          {"name": "create_user", "args": ["email", "password_hash"]}]})])

    prompts: list[str] = []

    def stub(spec: str, *a, **k) -> str:
        prompts.append(spec)
        if "Write a test for that code" in spec:
            return "from store import *\n\nprint('OK')\n"
        return ("def init_db():\n    pass\n\n\n"
                "def create_user(email, password_hash):\n    return 1\n")

    original = lp.generate_code
    lp.generate_code = stub
    try:
        _run_async(build_blueprint(blueprint, workspace=tmp_path, max_repairs=0))
    finally:
        lp.generate_code = original

    draft = prompts[0]
    assert "create_user(email, password_hash)" in draft, (
        f"the piece was held to a contract it was never shown:\n{draft}")
    assert "init_db()" in draft, draft


def test_the_test_prompt_gets_the_requirement_not_the_implementation_aids(tmp_path):
    """The codegen spec and the test spec want different things.

    The codegen spec accretes an entire worked exemplar page, the declared contract and
    every dependency's interface. None of that describes what the module must *do*, and a
    test prompt carrying a whole exemplar page invites the model to write about the
    exemplar.
    """
    import synapse_daemon.local_pipeline as lp
    from synapse_daemon.blueprints import CheckKind, Piece
    from synapse_daemon.scaffold.runner import build_blueprint
    from synapse_daemon.blueprints import Blueprint

    blueprint = Blueprint(
        id="t", name="t", summary="t",
        pieces=[Piece(name="store", spec="THE-REAL-REQUIREMENT", module="store",
                      checks=[CheckKind.UNIT, CheckKind.CONTRACT],
                      contract={"functions": [{"name": "init_db", "args": []}]})])

    prompts: list[str] = []

    def stub(spec: str, *a, **k) -> str:
        prompts.append(spec)
        if "Write a test for that code" in spec:
            return "from store import *\n\nprint('OK')\n"
        return "def init_db():\n    pass\n"

    original = lp.generate_code
    lp.generate_code = stub
    try:
        _run_async(build_blueprint(blueprint, workspace=tmp_path, max_repairs=0))
    finally:
        lp.generate_code = original

    draft = prompts[0]
    test_prompt = next(p for p in prompts if "Write a test for that code" in p)

    assert "THE-REAL-REQUIREMENT" in test_prompt, "the test prompt lost the requirement"
    assert "MUST expose exactly these" in draft, "the draft lost the contract"
    assert "MUST expose exactly these" not in test_prompt, (
        "the test prompt is still carrying the codegen scaffolding:\n" + test_prompt[:400])


def test_identical_code_is_resampled_before_the_loop_gives_up(tmp_path):
    """Greedy decoding repeats itself by construction; that is not the model giving up.

    Measured: `storage` stopped after two of ten allowed repairs with "the model stopped
    changing the code", having never once reached its acceptance scenario.
    """
    import synapse_daemon.local_pipeline as lp

    temperatures: list[float] = []

    def stub(spec: str, model: str = "", timeout: float = 900.0, num_ctx: int = 8192,
             temperature: float = 0.0) -> str:
        if "Write a test for that code" in spec:
            return "from solution import *\n\nassert broken() == 1\nprint('OK')\n"
        if "Running the tests produced" in spec:
            temperatures.append(temperature)
            # Deterministic until the sampler is actually turned up, exactly like the real
            # thing: same prompt, same answer.
            if temperature == 0.0:
                return "def broken():\n    return 0\n"
            return "def broken():\n    return 1\n"
        return "def broken():\n    return 0\n"

    original = lp.generate_code
    lp.generate_code = stub
    try:
        result = _run_async(run_pipeline("spec", workspace=tmp_path, max_repairs=2))
    finally:
        lp.generate_code = original

    assert temperatures[0] == 0.0, "the first repair should still be the model's best guess"
    assert temperatures[1] == lp.RESAMPLE_TEMPERATURES[0], (
        f"an identical repair was not resampled at a raised temperature: {temperatures}")
    assert result.passed, (
        f"resampling produced a working fix but the loop did not use it: "
        f"{result.stop_reason}")
    assert result.attempts[0].resamples == 1, "the resample was not recorded on the attempt"


def test_giving_up_says_how_many_samples_were_drawn(tmp_path):
    """A model that repeats itself at every temperature and on a rewrite has run out."""
    import synapse_daemon.local_pipeline as lp

    def stub(spec: str, model: str = "", timeout: float = 900.0, num_ctx: int = 8192,
             temperature: float = 0.0) -> str:
        if "Write a test for that code" in spec:
            return "from solution import *\n\nassert broken() == 1\nprint('OK')\n"
        return "def broken():\n    return 0\n"

    original = lp.generate_code
    lp.generate_code = stub
    try:
        result = _run_async(run_pipeline("spec", workspace=tmp_path, max_repairs=2))
    finally:
        lp.generate_code = original

    assert not result.passed
    assert "identical code across 4 samples" in result.stop_reason, result.stop_reason
    assert result.attempts[0].resamples == len(lp.RESAMPLE_TEMPERATURES)
    assert result.attempts[0].started_over


def test_a_stuck_repair_is_asked_to_start_over_without_the_code_to_copy(tmp_path):
    """Raising temperature cannot unstick a prompt whose output is mostly copying.

    Measured on `storage`: byte-identical ~3.8 KB output at 0, 0.4 and 0.8, from a model
    that demonstrably does vary at those temperatures on other prompts. The repair prompt
    hands over the whole current file and asks for a corrected copy, so the distribution
    stays peaked. The last resort removes the thing being copied.
    """
    import synapse_daemon.local_pipeline as lp

    prompts: list[str] = []

    def stub(spec: str, model: str = "", timeout: float = 900.0, num_ctx: int = 8192,
             temperature: float = 0.0) -> str:
        if "Write a test for that code" in spec:
            return "from solution import *\n\nassert broken() == 1\nprint('OK')\n"
        prompts.append(spec)
        # Identical however hot it gets - only a differently-shaped prompt escapes.
        if "write the module fresh" in spec:
            return "def broken():\n    return 1\n"
        return "def broken():\n    return 0\n"

    original = lp.generate_code
    lp.generate_code = stub
    try:
        result = _run_async(run_pipeline("spec", workspace=tmp_path, max_repairs=2))
    finally:
        lp.generate_code = original

    rewrite = [p for p in prompts if "write the module fresh" in p]
    assert rewrite, "the loop never tried a differently-shaped prompt"
    assert "Current code:" not in rewrite[0], (
        "the start-over prompt still pastes in the code the model keeps copying")
    assert "A previous attempt failed with" in rewrite[0], (
        "the start-over prompt dropped the failure, so the model can repeat the mistake")
    assert result.passed, f"the rewrite fixed it but the loop did not use it: {result.stop_reason}"
    assert result.attempts[0].started_over


def test_a_repair_is_never_graded_against_cached_bytecode(tmp_path):
    """A same-size rewrite inside one mtime tick used to be served from __pycache__.

    Python compares source mtime in whole seconds plus size, and repairs routinely rewrite
    a module to the same length within the same second. The test then ran the *previous*
    attempt's code and attributed the result to the fix just written.
    """
    from synapse_daemon.local_pipeline import _run

    (tmp_path / "solution.py").write_text("def broken():\n    return 0\n", encoding="utf-8")
    (tmp_path / "_t.py").write_text(
        "from solution import *\n\nassert broken() == 1, 'still zero'\n", encoding="utf-8")

    ok, _ = _run(tmp_path / "_t.py", tmp_path)
    assert not ok, "the first version should fail"

    # Same byte length, immediately afterwards - the exact shape of a real repair.
    (tmp_path / "solution.py").write_text("def broken():\n    return 1\n", encoding="utf-8")
    ok, error = _run(tmp_path / "_t.py", tmp_path)
    assert ok, f"the repair was graded against stale bytecode: {error}"


def test_each_piece_keeps_its_own_test_file(tmp_path):
    """Two pieces in one workspace must not overwrite each other's evidence."""
    import synapse_daemon.local_pipeline as lp

    original = lp.generate_code
    lp.generate_code = lambda spec, model="": "def noop():\n    pass\n"
    try:
        for module in ("passwords", "storage"):
            _run_async(run_pipeline("spec", workspace=tmp_path, path=f"{module}.py",
                                    max_repairs=0, runner=lambda p, c: (True, "")))
    finally:
        lp.generate_code = original

    written = sorted(p.name for p in tmp_path.glob("_test_*.py"))
    assert written == ["_test_passwords.py", "_test_storage.py"], (
        f"pieces shared a test filename and clobbered each other: {written}")
