# Tab Member — Productivity + Plan vs Actual theo member × ngày

Ngày: 2026-09-28 · Nhánh: `feature/database`

## Mục tiêu

Đổi tab **Productivity** thành tab **Member**, trả lời hai câu hỏi về từng người trong team:

1. **Năng suất** — mỗi người execute được bao nhiêu case, bao nhiêu case/ngày (bảng Productivity hiện có).
2. **So với plan** — từng ngày và cộng dồn cả phase, mỗi người nhanh/chậm bao nhiêu case so với
   Planning, và có làm đúng phần việc được giao không.

Thành công khi: đọc một hàng là biết người đó đang +/− bao nhiêu case, ngày nào lệch, lệch ở slot
nào; và các con số trên tab Member, Daily và Planning **không mâu thuẫn nhau**.

## Định nghĩa (đã chốt)

### Quy tắc toàn app: "so với plan → worked, đo năng suất → executed"

- **worked** = `STATUS.worked` = `counted − remaining` (as shipped: OK, NG, NG-OK, Cancel có PIC).
  Mọi con số **so với plan** dùng worked: ô ma trận, Δ, Bám plan %, Attainment, cột Attain của
  Daily, `calendar_view`, `day_view`. Planning vốn đã dùng worked — không đổi.
- **executed** = `STATUS.executed` (OK, NG, NG-OK). Mọi con số **năng suất** dùng executed: cột
  status, Executed, Working days, Cases/day, NG rate của Productivity; cột và thanh Executed của Daily.
- Lý do: plan 100 → 90 OK + 10 Cancel phải đọc là **đạt plan** ở mọi màn hình (Cancel là phạm vi bị
  cắt, không còn là việc phải làm), trong khi năng suất vẫn là 90 case đã test. Pending là
  `remaining` → chưa xong → tính là thiếu.

### Khoảng thời gian

- `today` = ngày server. `through` = hôm qua (today − 1 ngày lịch).
- **Mọi tổng** (ma trận, Productivity, Attainment) tính các ngày `≤ through`. Hôm nay đang làm dở nên
  không cộng — một ngày mới làm nửa buổi sẽ kéo Cases/day xuống sai và làm ai cũng "chậm" buổi sáng.
- **Không giới hạn đầu**: actual trước ngày bắt đầu phase vẫn được tính (quyết định của user). Hệ quả
  đã biết: việc làm trước phase không có plan, nên đẩy Δ về phía "nhanh".
- Case không có `test_date` và case ngoài plan (`in_plan`) bị loại, như `daily_rows` /
  `productivity_rows` hiện nay.

### Chỉ số của một member (tính đến `through`)

| Chỉ số | Định nghĩa |
|---|---|
| **Plan** | Σ `planned` của mọi plan entry của member có ngày `≤ through` (phase active) |
| **Actual** | Σ worked của member, mọi ngày `≤ through` — kể cả ngày không có plan, cuối tuần, trước phase |
| **Δ** | Actual − Plan. `null` khi Plan = 0 (không có mục tiêu để so) |
| **Bám plan %** | Với mỗi slot (file, device) member được plan: `min(Σ worked của member trên slot ≤ through, Σ plan slot ≤ through)`; cộng lại / Plan. Chặn 100%. `null` khi Plan = 0 |
| **Ngoài plan** | Σ worked của member vào những ngày `≤ through` mà member **không có** plan entry nào ngày đó |
| **Executed / Cancel** | Phần executed và phần worked-không-executed của Actual. **Executed + Cancel = Actual** |
| **Attainment** | Actual / Plan (0–∞), `null` khi Plan = 0 |

Bám plan cộng dồn theo slot nên: chậm rồi bù hôm sau → 100%; làm trước → 100%; vượt plan → vẫn
100% (phần vượt nằm ở Δ). Người khác làm bù không nâng Bám plan của member — slot đó đủ hay chưa
là việc của Planning.

**Team**: Plan/Actual/Executed/Cancel/Ngoài plan = tổng các hàng (kể cả N/A); Δ = Actual − Plan;
Bám plan = Σ min / Σ Plan của các member có plan; Attainment = Actual / Plan.

### Ô (member, ngày)

Server trả `state` và mọi con số; JS chỉ đổi dấu/trạng thái thành tone.

| Điều kiện | Nội dung ô |
|---|---|
| ngày `< today`, có plan | `planned`, `actual`, `delta = actual − planned`, `short[]` |
| ngày `< today`, không có plan, actual > 0 | `planned: null`, `actual`, `delta: null` → hiển thị "ngoài plan" |
| ngày `== today` | `planned`, `actual`, `delta: null`, `state: "today"` → "đang làm" |
| ngày `> today` | `planned`, `actual: null`, `state: "future"` |
| không plan, không actual | ô không có trong response |

`short[]` = các slot của member ngày đó có `worked < planned`: `{file, device, planned, actual}`.
Chỉ cho ngày `< today`. Hiển thị là dấu ⚠, hover liệt kê slot.

Mỗi ô còn mang `executed` và `cancel` để tooltip ghi "90 executed + 10 cancel".

### Hàng và cột

- **Hàng** = roster phase active ∪ pic có trong plan ∪ pic có actual. `N/A` (case không có PIC) là
  một hàng `aside: true`, chỉ có actual, Δ/Bám plan là `null`; hàng này làm tổng team khớp với
  Productivity.
- **Cột ngày** = chỉ **thứ 2 – thứ 6**. Không có setting cuối tuần (user: tạm thời không quan tâm).
  **Giới hạn đã biết**: worked vào T7/CN vẫn vào Actual/Ngoài plan (là việc thật), nhưng không có cột
  để hiện — hàng khi đó cộng không đủ tổng đúng bằng phần cuối tuần.
- **Tuần** = thứ 2 → thứ 6. Danh sách tuần = các tuần giao với [phase start, phase end] ∪ các tuần
  chứa một ngày thường có plan hoặc actual; sắp xếp tăng dần, tuần trống ở giữa bỏ qua. Mỗi tuần luôn
  đủ 5 ngày, mỗi ngày mang `in_phase`. `current` = tuần chứa today (today rơi vào cuối tuần → tuần
  của thứ 2 trước đó); nếu không có trong danh sách → tuần gần nhất trước đó, không có nữa → tuần đầu.

## API

Tất cả là `jsonify` wrapper trong blueprint mới `tcm/web/blueprints/member.py`. Mọi phép tính ở
service. Mọi response mang `today` và `through` để đối chiếu các request tách rời. Không có gì
được load → cấu trúc rỗng (không lỗi), như `/api/productivity` hiện nay.

| Endpoint | Trả về | JS gọi khi |
|---|---|---|
| `GET /api/member/productivity` | `{today, through, rows: [...], team}`; mỗi row = `productivity_rows` + `cancel` (và key từng status worked-không-executed) + `worked` + `ng_rate` (null khi không execute gì hoặc taxonomy không có status fail) + `attainment` + `planned` | load/reload/mở snapshot, lưu plan, đổi phase, lưu taxonomy |
| `GET /api/member/totals` | `{today, through, members: [{pic, aside, planned, actual, delta, adherence, unplanned, executed, cancel}], team}` | như trên |
| `GET /api/member/weeks` | `{today, through, weeks: [{start, label, days: [{date, in_phase}]}], current}` | như trên |
| `GET /api/member/week/<YYYY-MM-DD>` | `{today, through, start, days, cells: {pic: {date: cell}}, team: {date: {planned, actual, delta}}}` | mỗi lần đổi tuần (và sau các sự kiện trên, cho tuần đang xem) |

- `<YYYY-MM-DD>` phải là ngày hợp lệ và là thứ 2 → không thì 400 với message của `parse_date` / "must
  be a Monday". Một thứ 2 hợp lệ ngoài danh sách tuần vẫn được trả lời (các ô rỗng).
- `/api/productivity` bị **xoá** (không giữ alias). `fetchAll` bỏ phần productivity.
- `/api/plan` (`calendar_view`): bỏ `by_pic` và `actual_by_pic`; `actual` đổi sang worked.

## Backend

### `tcm/services/aggregation.py`

- `daily_rows`: mỗi row thêm `executed` và `worked` (đếm theo `STATUS.executed` / `STATUS.worked`),
  để Daily và các service đọc thẳng thay vì cộng lại cờ taxonomy.
- `productivity_rows(cases, until=None)`: bỏ case có `test_date > until`; mỗi row thêm key cho mỗi
  status trong `STATUS.worked − STATUS.executed` và `worked`. Công thức `executed`/`days`/
  `productivity` giữ nguyên.

### `tcm/services/members.py` (mới) — `MemberService`

Tách khỏi `planning.py` (đã 579 dòng) nhưng dùng lại nó: `MemberService(planning, today=None)`, đọc
phase qua `planning.get_settings(cases)`, plan qua `planning.repository.days()`, roster qua
`planning.repository.members()`; `today` mặc định là hàm today của planning (inject được cho test).

- `_Facts` nội bộ, dựng một lần mỗi request từ `daily_rows(cases)` + plan: worked/executed theo
  `(pic, date)` và `(pic, slot, date)`, plan theo `(pic, date)` và `(pic, slot, date)`.
- `_totals(facts)` — **nơi duy nhất** tính Plan/Actual/Δ/Bám plan/Ngoài plan/Attainment theo member
  và team. `productivity()` và `totals()` đều gọi nó.
- Public: `productivity(cases)`, `totals(cases)`, `weeks(cases)`, `week(cases, monday)`.

`calendar_view` và `day_view` trong `planning.py` đổi `_actuals` sang worked. Comment đầu
`planning.py` (dòng ~30) viết lại theo quy tắc mới.

### Composition root

`create_app` dựng `MemberService(planning)` và đặt lên `app.extensions`; blueprint gọi qua helper
`member_report()` trong `tcm/web/blueprints/__init__.py` (không đặt tên `member()` — import module
blueprint `member` sẽ ghi đè tên đó, cùng lý do helper phase là `phase_service()`).

## Frontend

- `main.js`: `VIEWS.productivity` → `VIEWS.member` (title "Member"); rail đổi nhãn.
  `templates/views/productivity.html` → `templates/views/member.html` (include trong `index.html`).
- `static/js/views/productivity.js` → thư mục `static/js/views/member/`:
  - `index.js` — module duy nhất `main.js` import; gọi 4 hàm mới trong `api.js`, giữ tuần đang xem,
    tải lại khi `refreshViews`, `onPlanChange` và khi quay lại tab.
  - `productivity.js` — vẽ bảng Productivity: status executed (band), **Cancel** (`band--aside`),
    Executed, Working days, Cases/day, NG rate, Attainment; dòng Team lấy từ `team`. Không còn
    `failRate`, không còn cộng footer ở JS. Sort vẫn ở JS (thứ tự hiển thị).
  - `matrix.js` — pager tuần (‹ nhãn tuần › + "Tuần này"), bảng member × 5 ngày ║ Plan · Actual ·
    Δ · Bám plan · Ngoài plan; dòng Team; hàng N/A `row--aside`; cột tổng sort được. Tone: Δ > 0
    success, < 0 danger, 0 neutral; Bám plan/Attainment ≥ 100% success, ≥ 80% warn, còn lại danger.
    Nhãn nhóm cột tổng ghi "đến <through>".
- Heatmap bị xoá (markup, `renderHeatmap`, CSS `.heat*` không còn ai dùng).
- `plan.js`: bỏ `byPic`, `actualByPic`, `plannedForPic`, `actualForPic`, `planTotals`.
- `views/daily.js`: Attain và tone của thanh dùng Σ `row.worked` / plan; cột và thanh Executed vẫn
  `executedIn`. Tooltip thanh ghi cả worked khi khác executed.
- Mọi `fetch` nằm trong `api.js`; `views/member/**` không import view khác.

## Test

`tests/services/test_members.py` (mới):
- 90 OK + 10 Cancel vs plan 100 → Actual 100, Δ 0, Attainment 1.0, Executed 90, Cancel 10.
- Bốn tình huống Bám plan (plan 30/ngày × 2 ngày): 20+30 → 83%, 20+40 → 100%, 40+20 → 100%,
  40+40 → 100% với Δ +20.
- Ngày cùng slot khác: plan file-1 30, làm file-1 20 + file-2 10 → ô Δ 0, `short` = file-1 20/30.
- Hôm nay không vào tổng; ngày tương lai không vào tổng; ngày không plan vào Actual và Ngoài plan,
  ô có `delta: null`; actual trước phase start được tính.
- Pending không được tính vào Actual.
- **Đối chiếu**: với mọi member, `productivity.executed + cancel == totals.actual`; tổng các ô ngày
  thường `≤ through` qua mọi tuần + worked cuối tuần `== totals.actual`; team = tổng các hàng.
- Tuần: chỉ thứ 2–6, `in_phase` đúng, `current` đúng khi today là thứ 7; 400 khi không phải thứ 2.

Sửa test có sẵn: `test_aggregate.py` (row mới của `daily_rows`/`productivity_rows`, `until`),
`test_planning.py` (`calendar_view` không còn `by_pic`, actual là worked; `day_view` worked),
`tests/web/test_api.py` (`/api/productivity` → `/api/member/*`), test layering/app nếu đụng tới
danh sách view hoặc blueprint.

## Tài liệu

Cập nhật `CLAUDE.md`: danh sách view (Productivity → Member), mục Productivity/heatmap, mục
`plan.js` (bỏ per-PIC), đoạn "The planner counts worked" (quy tắc mới áp cho cả `day_view` /
`calendar_view` / Daily), "Aggregation is shared" (endpoint mới), frontend state ownership.

## Ngoài phạm vi

- Setting / tuần làm việc có T7, CN (Planning vẫn T2–T6 cứng trong `tcm/domain/plan.py`).
- Nhập lý do lệch plan.
- Đưa bộ lọc của Daily lên server. (Attain của Daily vẫn so Σ worked **đã lọc** với plan **cả
  ngày** — lệch sẵn có khi lọc, không sửa ở đây.)
