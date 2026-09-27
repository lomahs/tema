"""compare_cases: what changed between two loads."""
from tcm.domain.case import TestCase as Case
from tcm.domain.status import STATUS
from tcm.services.aggregation import compare_cases


def case(row, result, scope="FPT", file="A.xlsx", device="iPhone", pic="An"):
    return Case(file_name=file, sheet="S", device=device, row_num=row,
                scope=scope, result=result, pic=pic)


def key_of(result):
    return STATUS.classify_case(case(1, result))


def test_moves_are_counted_and_everything_is_accounted_for(fixed_scopes):
    base = [case(1, None), case(2, None), case(3, "OK")]
    head = [case(1, "OK"), case(2, None), case(4, "NG")]
    out = compare_cases(base, head)
    moves = {(t["from"], t["to"]): t["count"] for t in out["transitions"]}
    assert moves == {(key_of(None), key_of("OK")): 1,     # row 1 ran
                     (key_of("OK"), None): 1,             # row 3 removed
                     (None, key_of("NG")): 1}             # row 4 added
    assert out["unchanged"] == 1                          # row 2
    assert sum(moves.values()) + out["unchanged"] == 4    # rows 1-4, once each


def test_totals_and_rows_carry_deltas(fixed_scopes):
    out = compare_cases([case(1, None)], [case(1, "OK"), case(2, "OK", device="iPad")])
    ok = key_of("OK")
    assert out["totals"][ok] == {"base": 0, "head": 2, "delta": 2}
    assert out["total"]["delta"] == 1
    [ipad] = [r for r in out["rows"] if r["device"] == "iPad"]
    assert ipad["base"]["total"] == 0 and ipad["head"][ok] == 1 and ipad["delta"][ok] == 1


def test_work_outside_the_plan_is_not_compared(fixed_scopes):
    # JP is excluded in FIXED_SCOPES.
    out = compare_cases([case(1, None, scope="JP")], [case(1, "OK", scope="JP")])
    assert out["transitions"] == [] and out["rows"] == [] and out["total"]["head"] == 0
