"""compare_cases: what changed between two loads."""
import pytest

from tcm.domain.case import TestCase as Case
from tcm.domain.scope import SCOPES, ScopeSet
from tcm.domain.status import STATUS
from tcm.services.aggregation import compare_cases, compared_cases


def case(row, result, scope="FPT", file="A.xlsx", device="iPhone", pic="An"):
    return Case(file_name=file, sheet="S", device=device, row_num=row,
                scope=scope, result=result, pic=pic)


def key_of(result, pic="An"):
    return STATUS.classify_case(case(1, result, pic=pic))


def side(state):
    return None if state is None else (state["scope"], state["status"])


def moves(out):
    return {(side(t["from"]), side(t["to"])): t["count"] for t in out["transitions"]}


def only_move(out):
    [move] = out["transitions"]
    return move


@pytest.fixture
def two_counted():
    """FPT and JM both count, JP does not — for a scope move that stays in plan."""
    saved = dict(SCOPES.__dict__)
    SCOPES.adopt(ScopeSet.from_dict({
        "groups": [
            {"key": "FPT", "label": "FPT", "match": ["FPT"]},
            {"key": "JM", "label": "JM Support", "match": ["FPT (JM Support)"]},
            {"key": "JP", "label": "JP", "match": ["JP"], "excluded": True},
        ],
        "fallback": {"key": "Other", "label": "Other"},
    }))
    yield SCOPES
    SCOPES.__dict__.clear()
    SCOPES.__dict__.update(saved)


def test_moves_are_counted_and_everything_is_accounted_for(fixed_scopes):
    base = [case(1, None), case(2, None), case(3, "OK")]
    head = [case(1, "OK"), case(2, None), case(4, "NG")]
    out = compare_cases(base, head)
    assert moves(out) == {(("FPT", key_of(None)), ("FPT", key_of("OK"))): 1,  # row 1 ran
                          (("FPT", key_of("OK")), None): 1,                   # row 3 removed
                          (None, ("FPT", key_of("NG"))): 1}                   # row 4 added
    assert out["unchanged"] == 1                                              # row 2
    assert sum(moves(out).values()) + out["unchanged"] == 4                   # rows 1-4, once each


def test_totals_and_rows_carry_deltas(fixed_scopes):
    out = compare_cases([case(1, None)], [case(1, "OK"), case(2, "OK", device="iPad")])
    ok = key_of("OK")
    assert out["totals"][ok] == {"base": 0, "head": 2, "delta": 2}
    assert out["total"]["delta"] == 1
    [ipad] = [r for r in out["rows"] if r["device"] == "iPad"]
    assert ipad["base"]["total"] == 0 and ipad["head"][ok] == 1 and ipad["delta"][ok] == 1


def test_work_outside_the_plan_on_both_sides_is_not_compared(fixed_scopes):
    # JP is excluded in FIXED_SCOPES.
    out = compare_cases([case(1, None, scope="JP")], [case(1, "OK", scope="JP")])
    assert out["transitions"] == [] and out["unchanged"] == 0
    assert out["rows"] == [] and out["total"]["head"] == 0


def test_a_case_moved_out_of_scope_is_a_move_not_a_removal(fixed_scopes):
    out = compare_cases([case(1, "OK")], [case(1, "OK", scope="JP")])
    move = only_move(out)
    assert (side(move["from"]), side(move["to"])) == (("FPT", key_of("OK")), ("JP", key_of("OK")))
    assert move["plan"] == "left"
    assert move["scope_changed"] and not move["status_changed"]
    assert out["total"] == {"base": 1, "head": 0, "delta": -1}   # Total still Summary's


def test_a_case_moved_into_scope_enters_the_plan(fixed_scopes):
    move = only_move(compare_cases([case(1, None, scope="JP")], [case(1, None)]))
    assert move["plan"] == "entered" and move["scope_changed"]


def test_cancel_losing_its_pic_leaves_the_plan_by_status(fixed_scopes):
    move = only_move(compare_cases([case(1, "対象外")], [case(1, "対象外", pic=None)]))
    assert side(move["to"]) == ("FPT", key_of("対象外", pic=None))
    assert move["plan"] == "left"
    assert move["status_changed"] and not move["scope_changed"]


def test_a_scope_move_between_counted_groups_stays_in_plan(two_counted):
    move = only_move(compare_cases([case(1, "OK")], [case(1, "OK", scope="FPT (JM Support)")]))
    assert (side(move["from"]), side(move["to"])) == (("FPT", key_of("OK")), ("JM", key_of("OK")))
    assert move["plan"] is None and move["scope_changed"]


def test_a_spelling_inside_one_group_is_not_a_move(fixed_scopes):
    # "FPT (JM Support)" is FPT in FIXED_SCOPES: the group is what is compared.
    out = compare_cases([case(1, "OK")], [case(1, "OK", scope="FPT (JM Support)")])
    assert out["transitions"] == [] and out["unchanged"] == 1


def test_added_and_removed_rows_carry_no_plan_direction(fixed_scopes):
    out = compare_cases([case(1, "OK")], [case(2, "OK")])
    assert {t["plan"] for t in out["transitions"]} == {None}


def test_compared_cases_lists_one_move_with_both_sides(fixed_scopes):
    base = [case(1, "OK"), case(2, "OK"), case(3, "OK")]
    head = [case(1, "OK", scope="JP", pic="Bo"), case(2, "NG"), case(3, "OK")]
    rows = compared_cases(base, head, ("FPT", key_of("OK")), ("JP", key_of("OK")))
    assert rows == [{
        "file": "A.xlsx", "sheet": "S", "device": "iPhone", "row": 1, "case_no": None,
        "base": {"scope": "FPT", "scope_group": "FPT", "result": "OK", "pic": "An",
                 "status": key_of("OK")},
        "head": {"scope": "JP", "scope_group": "JP", "result": "OK", "pic": "Bo",
                 "status": key_of("OK")},
    }]


def test_compared_cases_lists_added_rows_with_no_base(fixed_scopes):
    rows = compared_cases([], [case(7, "NG")], None, ("FPT", key_of("NG")))
    assert [(r["row"], r["base"]) for r in rows] == [(7, None)]


def test_every_move_lists_exactly_its_count(fixed_scopes):
    base = [case(i, None) for i in range(1, 6)] + [case(9, "OK", scope="JP")]
    head = [case(1, "OK"), case(2, "OK"), case(3, "NG"), case(4, None, scope="JP"),
            case(6, "OK"), case(9, "OK")]
    out = compare_cases(base, head)
    for t in out["transitions"]:
        listed = compared_cases(base, head, side(t["from"]), side(t["to"]))
        assert len(listed) == t["count"]


def test_compared_cases_come_in_row_order(fixed_scopes):
    base = [case(10, None), case(2, None)]
    head = [case(10, "OK"), case(2, "OK")]
    rows = compared_cases(base, head, ("FPT", key_of(None)), ("FPT", key_of("OK")))
    assert [r["row"] for r in rows] == [2, 10]


def test_the_answer_names_every_scope_group(fixed_scopes):
    out = compare_cases([], [])
    assert [(g["key"], g["counted"]) for g in out["scopes"]] == \
        [("FPT", True), ("JP", False), ("Other", False)]
