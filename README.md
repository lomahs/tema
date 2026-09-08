# Test Case Management

Flask web app đọc test case từ các file Excel (.xlsx) và tổng hợp tiến độ / kết quả test.

## Cấu trúc

```
test-case-management/
├── app.py                  # Flask app factory + route "/"
├── config.py               # PORT, DEBUG, đường dẫn config, thiết lập Graph
├── aggregate.py            # tổng hợp summary / daily / productivity / issues
├── requirements.txt
├── api/
│   └── routes.py           # Blueprint /api/* + in-memory store
├── report/
│   ├── layout.py           # ReportLayout: cột nào của file báo cáo giữ gì
│   ├── report_layout.json  # cấu hình layout mặc định
│   ├── builder.py          # dòng tổng hợp -> lưới ô theo layout
│   └── publisher.py        # ghi 3 bảng vào workbook trên SharePoint
├── sharepoint/
│   ├── auth.py             # đăng nhập device code (MSAL), cache token
│   ├── client.py           # HTTP client cho Graph, retry khi bị throttle
│   ├── links.py            # URL SharePoint -> driveItem
│   └── workbook.py         # sửa workbook tại chỗ qua Excel workbook API
├── parser/
│   ├── models.py           # SheetConfig, TestCase (dataclass)
│   ├── status.py           # StatusSet: result -> status
│   ├── result_status.json  # cấu hình phân loại kết quả
│   ├── scope_groups.json   # cấu hình nhóm Scope (Summary tách bảng)
│   └── excel_reader.py     # đọc TOOL_DATA + test case từ .xlsx
├── tools/
│   ├── generate_samples.py # sinh file .xlsx mẫu
│   ├── publish_report.py   # xuất báo cáo lên SharePoint từ dòng lệnh
│   └── sample_config.json  # config mặc định cho generator
├── tests/
│   ├── conftest.py             # helper dựng file .xlsx cho test
│   ├── test_status.py
│   ├── test_excel_reader.py
│   ├── test_api.py
│   ├── test_aggregate.py
│   ├── test_report_layout.py
│   ├── test_report_builder.py
│   ├── test_publisher.py
│   ├── test_publish_integration.py
│   ├── test_sharepoint_*.py
│   ├── test_api_sharepoint.py
│   └── test_generate_samples.py
├── templates/
│   └── index.html          # UI 3 tab: Summary / Daily / Detail
└── static/
    ├── css/
    │   ├── tokens.css      # design token: màu, chữ, khoảng cách, dark mode
    │   └── app.css         # component: ledger, status band, drawer, pager
    └── js/                 # ES modules, nạp qua <script type="module">
        ├── main.js         # entry point: wiring + chuyển tab
        ├── dom.js          # $, $$, esc
        ├── api.js          # mọi lời gọi fetch tới /api/*
        ├── theme.js        # sáng/tối, đọc token CSS ra màu cụ thể
        ├── setupDrawer.js  # ngăn Setup + dòng tóm tắt nguồn trên thanh trên
        ├── sourcePanel.js  # chọn folder/file, Load & Reload, localStorage
        ├── reportPanel.js  # đăng nhập SharePoint + nút Publish
        ├── taxonomy.js     # status từ /api/statuses + scaffolding bảng
        ├── groupedTable.js # bảng gộp nhóm, đóng/mở, dòng cha cộng dồn
        ├── sorting.js      # sort theo cột (asc -> desc -> bỏ sort)
        ├── filters.js      # uniqueOf, populateSelect
        ├── pagination.js   # phân trang (theo dòng hoặc theo nhóm)
        ├── charts.js       # Chart.js, màu lấy từ tone của taxonomy
        └── views/
            ├── summary.js  # gộp theo file, mở ra thành device
            ├── daily.js    # tiến độ theo ngày, gộp theo ngày
            ├── productivity.js # năng suất theo thành viên
            └── detail.js   # stat, filter, tìm kiếm, bảng, phân trang
```

## Chạy

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5000
```

## Tạo file mẫu

Sinh file test case `.xlsx` giả lập để thử tool mà không cần dữ liệu thật:

```bash
python -m tools.generate_samples --out samples/generated
```

Đọc config từ `tools/sample_config.json` (đổi bằng `--config`):

| Key | Mô tả |
|-----|-------|
| `file_count` | Số file .xlsx sinh ra |
| `sheets_per_file` | Số sheet tối đa mỗi file — số thực tế random từ 1 đến giá trị này |
| `devices_per_sheet` | Số device tối đa mỗi sheet — số thực tế random từ 1 đến giá trị này (random lại cho từng sheet) |
| `cases_per_sheet` | `{min, max}` — số test case mỗi sheet (random trong khoảng) |
| `pic_names` | Danh sách tên PIC |
| `seed` | Cố định seed để sinh lại y hệt (`null` = ngẫu nhiên) |
| `file_prefix`, `sheet_names`, `device_names` | Pool tên file / sheet / device |
| `scopes` | Giá trị cột Scope — mặc định `FPT`, `FPT (JM Support)`, `JP` |
| `result_weights` | Tỉ trọng các Result: `OK`, `NG`, `NG-OK`, `保留`, `対象外`, `""` (rỗng) |
| `missing_reason_rate` | Tỉ lệ dòng NG/NG-OK/保留/対象外 **thiếu** Ticket ID lẫn Note |
| `no_pic_rate` | Tỉ lệ dòng `対象外` bị bỏ trống PIC — tức sinh ra case **Out Of Scope** |
| `group_row_rate` | Tỉ lệ chèn dòng tiêu đề nhóm (không phải test case) |
| `date_range` | `[start, end]` — khoảng ngày cho cột Test Date |

Ghi đè nhanh bằng flag, không cần sửa config:

```bash
python -m tools.generate_samples --files 5 --sheets 4 --devices 3 \
    --min-cases 30 --max-cases 60 --pics "lee,kim,tanaka" --out ./generated
```

Bố cục sheet sinh ra: cột `A` = Test No (số, đánh lại từ 1 ở mỗi sheet),
cột `B` = Scope, sau đó mỗi device chiếm 1 khối 5 cột
(Result / Test Date / PIC / Ticket ID / Note) bắt đầu từ `C`, `H`, `M`...
Dữ liệu bắt đầu ở dòng 4.

Dòng tiêu đề nhóm (ví dụ `[Login - permission]`) nằm trong vùng
`start_row..end_row` nên tool vẫn đọc thành 1 dòng không có Result → tính là
`NYS`. Đây là chủ ý, giống file test case thật.

## Định dạng file Excel

Mỗi file .xlsx phải có sheet tên `TOOL_DATA`, gồm các cột (không phân biệt hoa thường):

| sheet | device | start_row | end_row | test_no_col | scope_col | result_col | test_date_col | pic_col | ticket_id_col | note_col |
|-------|--------|-----------|---------|-------------|-----------|------------|---------------|---------|---------------|----------|
| TC_A  | DeviceA| 3         | 100     | A           | B         | C          | D             | E       | F             | G        |

Mỗi dòng trong `TOOL_DATA` mô tả một sheet test case: đọc từ `start_row` đến `end_row`,
lấy dữ liệu theo chữ cái cột Excel.

## API

| Method | Endpoint       | Mô tả |
|--------|----------------|-------|
| POST   | `/api/load`    | Body `{"folder": "..."}` hoặc `{"files": ["...", "..."]}` |
| POST   | `/api/reload`  | Nạp lại từ source đã load trước đó |
| GET    | `/api/data`    | Toàn bộ test case, kèm `status` đã phân loại |
| GET    | `/api/statuses`| Danh sách status (key / label / badge / text) + `needs_reason` + `executed` + `issue` |
| GET    | `/api/summary` | Gộp theo (nhóm Scope, file, device) + danh sách nhóm Scope + danh sách case thiếu lý do |
| GET    | `/api/daily`   | Gộp theo (file, device, PIC, date) |
| GET    | `/api/productivity` | Năng suất từng PIC: số case đã thực hiện / số ngày có làm việc |
| GET    | `/api/sharepoint/status` | `not_configured` / `signed_out` / `pending` / `signed_in` |
| POST   | `/api/sharepoint/login`  | Bắt đầu device code flow, trả `{user_code, verification_uri}` |
| POST   | `/api/sharepoint/logout` | Quên tài khoản đã cache |
| POST   | `/api/report/publish`    | Body `{"url": "<link SharePoint>", "run_date": "YYYY-MM-DD"?}` |

## Phân loại kết quả

Định nghĩa trong `parser/result_status.json` — backend, UI và tool sinh file mẫu đều đọc
từ đây, nên chỉ cần sửa một chỗ:

`OK` → OK · `NG` → NG · `NG-OK` → NG-OK · `保留` → Pending · `対象外` → Cancel ·
rỗng → NYS (not yet started) · còn lại → Other

Riêng `対象外` **không điền PIC** → **Out Of Scope**, không phải Cancel. Xem
[Out Of Scope](#out-of-scope-対象外-không-có-pic) bên dưới.

Mỗi status gồm:

| Key | Ý nghĩa |
|-----|---------|
| `key` | Tên cột trong `/api/summary`, `/api/daily` |
| `label` | Nhãn hiển thị trên UI |
| `match` | Các giá trị Result ánh xạ vào status này (không phân biệt hoa thường) |
| `tone` | Màu của status: `success` / `danger` / `warn` / `neutral` / `muted`. Dùng chung cho badge, số trong bảng và biểu đồ. Không khai báo = suy ra từ `badge` |
| `badge` | (cũ) Class Bootstrap. UI không còn đọc trường này; giữ lại để config cũ vẫn suy ra được `tone` |
| `text` | (cũ) Class Bootstrap cho màu chữ. UI không còn đọc trường này |
| `empty` | Đúng 1 status đánh dấu `true` — dùng cho ô Result rỗng |
| `fallback` | Đúng 1 status đánh dấu `true` — nhận mọi giá trị lạ |
| `executed` | Đánh dấu `true` = coi như đã thực hiện; chỉ các status này được tính vào năng suất |
| `issue` | Đánh dấu `true` = cần theo dõi; đúng các status này lên bảng Issues của báo cáo SharePoint (mặc định NG, Pending, Cancel) |
| `derive` | `{"from": "<status>", "when": "<điều kiện>"}` — status này không đọc từ ô Result mà **chuyển hoá** từ một status khác khi điều kiện đúng. Điều kiện hợp lệ hiện chỉ có `no_pic` |
| `excluded` | Đánh dấu `true` = vẫn có cột, nhưng **không cộng vào `total`** và không được có trong `needs_reason` |
| `review` | Đánh dấu `true` = case thuộc status này sẽ hiển thị ở tab **Detail**. Không được đặt cùng lúc với `excluded` |
| `needs_reason` | (cấp ngoài) Các status bắt buộc phải có Ticket ID hoặc Note |

Nhờ có `fallback`, không giá trị nào bị bỏ sót: mỗi case luôn rơi vào đúng một cột.
`total` của mỗi dòng bằng tổng các cột **không** bị `excluded`.

### Out Of Scope (`対象外` không có PIC)

Một case ghi `対象外` mà **bỏ trống PIC** không phải là một case bị huỷ có người chịu
trách nhiệm — nó là case **nằm ngoài phạm vi test**. App tách hai loại này ra:

| | `対象外` + có PIC | `対象外` + trống PIC |
|---|---|---|
| Status | `Cancel` | `Out Of Scope` |
| Cột trên Summary / Daily | có | có (ngay sau `NYS`, ngăn bằng vạch nét đứt) |
| Cộng vào `total` | có | **không** |
| Bị flag Missing Reason | có (nếu thiếu cả Ticket ID lẫn Note) | **không** |
| Lên danh sách Issue / sheet Issues | có | **không** |
| Cột trong báo cáo SharePoint | có | **không** (xem bên dưới) |

Vì `Out Of Scope` bị `excluded`, nó **không** sinh cột trong báo cáo SharePoint. Nhờ vậy
`total` trong báo cáo vẫn đúng bằng tổng các cột status của báo cáo, và file trên
SharePoint không phải chèn thêm cột nào.

Luật này khai báo trong `result_status.json`, không nằm trong code:

```json
{"key": "OOS", "label": "Out Of Scope",
 "derive": {"from": "Cancel", "when": "no_pic"}, "excluded": true, "tone": "muted"}
```

Màu cụ thể của mỗi `tone` nằm trong `static/css/tokens.css`, không nằm trong file JSON
này — đổi bảng màu không phải sửa taxonomy, và ngược lại. Nhiều status dùng chung một
`tone` là bình thường (OK và NG-OK đều là kết quả tốt); biểu đồ tự tách chúng ra bằng
cách làm đậm dần theo thứ tự trong taxonomy.

### Năng suất theo thành viên

Bảng dưới tab **Daily** tính cho từng PIC:

```
năng suất = số case có status `executed` / số ngày có ít nhất 1 case `executed`
```

Mặc định `executed` là `OK`, `NG`, `NG-OK`. Case không có Test Date bị bỏ qua hoàn toàn
(không vào tử số lẫn mẫu số); ngày chỉ có `保留` / `対象外` không được tính là ngày làm
việc. Case không ghi PIC gom vào dòng `N/A`. Bảng này luôn tính trên toàn bộ dữ liệu đã
nạp, không chịu ảnh hưởng của bộ lọc phía trên.

Dùng file cấu hình khác:

```bash
RESULT_STATUS_CONFIG=/path/to/my_status.json python app.py
SCOPE_GROUPS_CONFIG=/path/to/my_scopes.json python app.py
```

## Xuất báo cáo lên SharePoint

Ghi kết quả đã tổng hợp vào một file `.xlsx` **có sẵn** trên SharePoint, thành ba bảng:
Summary (theo file & device), Daily (theo ngày, file, device, PIC) và Issues (mọi case
NG / Pending / Cancel). App ghi **tại chỗ** qua Excel workbook API của Graph — file không
bị tải xuống rồi thay thế, nên định dạng, công thức, biểu đồ và pivot trong file báo cáo
còn nguyên.

Việc đọc test case vẫn hoàn toàn từ ổ đĩa local; Graph chỉ dùng cho việc ghi.

### 1. Đăng ký ứng dụng Azure

Cần một app registration để đăng nhập. Vào [Azure Portal](https://portal.azure.com) →
**Microsoft Entra ID** → **App registrations** → **New registration**:

- **Name**: gì cũng được, ví dụ `Test Case Management`.
- **Supported account types**: *Accounts in this organizational directory only*.
- **Redirect URI**: **để trống** — device code flow không cần.

Sau khi tạo:

- **Authentication** → **Advanced settings** → bật **Allow public client flows** = *Yes*.
  Thiếu bước này thì đăng nhập sẽ báo lỗi.
- **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated
  permissions** → thêm **`Files.ReadWrite.All`**. (`offline_access` MSAL tự xin, không cần
  thêm tay.) Nếu tenant bắt buộc thì nhờ admin bấm **Grant admin consent**.
- Chép **Application (client) ID** và **Directory (tenant) ID** ở tab **Overview**.

App chạy dưới danh nghĩa người đăng nhập, nên chỉ ghi được đúng những file người đó vốn có
quyền sửa.

### 2. Cấu hình

```bash
export GRAPH_CLIENT_ID=<Application (client) ID>
export GRAPH_TENANT_ID=<Directory (tenant) ID>   # mặc định "organizations"
python app.py
```

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `GRAPH_CLIENT_ID` | *(rỗng)* | Bắt buộc. Chưa đặt thì panel SharePoint báo rõ và không cho bấm. |
| `GRAPH_TENANT_ID` | `organizations` | Đặt tenant id để giới hạn đúng một directory. |
| `GRAPH_TOKEN_CACHE` | `~/.test-management/graph_token_cache.json` | Nơi lưu refresh token, ghi với quyền `0600`. Giữ như file mật khẩu. |
| `REPORT_LAYOUT_CONFIG` | `report/report_layout.json` | Layout file báo cáo. |

### 3. Dùng

1. Load test case từ folder local như bình thường.
2. Bấm **Sign in** → app hiện một mã; mở
   [microsoft.com/devicelogin](https://microsoft.com/devicelogin), nhập mã, đăng nhập.
   Token được cache nên thỉnh thoảng mới phải làm lại.
3. Copy link file báo cáo từ trình duyệt (nút **Copy link**, hoặc URL trên thanh địa chỉ)
   và dán vào ô **SharePoint report file**.
4. Bấm **Publish**.

Hoặc từ dòng lệnh, cùng một code path:

```bash
python -m tools.publish_report --folder samples/generated --url "<link SharePoint>"
python -m tools.publish_report --folder ... --url ... --run-date 2026-09-01
```

### Chạy nhiều lần trong ngày

Mỗi dòng ghi ra mang một cột `run_date`. Trước khi ghi, app **xoá mọi dòng có cùng
`run_date`** rồi mới nối dòng mới. Bấm Publish hai lần trong ngày cho ra đúng kết quả như
bấm một lần — không nhân đôi. Các ngày khác không bị đụng tới.

Điều này cũng là lý do một lần publish hỏng giữa chừng không nguy hiểm: **không có
rollback**, file có thể đã được ghi một phần, nhưng chạy lại sẽ dọn và ghi đúng.

### Layout file báo cáo

File đích phải **có sẵn** ba sheet cùng dòng tiêu đề; app không tự tạo sheet. Cột nào giữ
gì khai trong `report/report_layout.json`:

```json
{
  "sheets": [
    {
      "dataset": "summary",
      "sheet": "Summary",
      "header_row": 1,
      "first_column": "A",
      "columns": [
        {"field": "run_date"},
        {"field": "file"},
        {"field": "device"},
        {"field": "total"},
        {"expand": "statuses"}
      ]
    }
  ]
}
```

- `dataset`: `summary`, `daily` hoặc `issues`.
- `sheet`: tên sheet trong file báo cáo. Không tìm thấy → báo lỗi, **không ghi gì cả**
  (mọi sheet được kiểm tra trước khi ghi dòng đầu tiên).
- `header_row`: dòng tiêu đề. Dữ liệu ghi từ dòng ngay dưới vùng đã có.
- `first_column`: cột trái nhất được ghi; các cột nằm liền nhau sang phải.
- `columns`: theo thứ tự. Mỗi phần tử là `{"field": "..."}` hoặc `{"expand": "statuses"}`.
- `{"expand": "statuses"}` nở thành một cột cho mỗi status **theo thứ tự taxonomy** — thêm
  status mới vào `result_status.json` là báo cáo tự có thêm cột. Chỉ dùng được cho
  `summary` và `daily` (dòng `issues` là từng case, không phải nhóm đếm). Status có
  `"excluded": true` **không** sinh cột, nên các cột status trong báo cáo luôn cộng đúng
  bằng `total` của nó.
- Mỗi sheet phải có **đúng một** cột `run_date` — đó là khoá chống trùng.

Field theo từng dataset:

| dataset | field |
|---------|-------|
| `summary` | `run_date`, `file`, `device`, `total` |
| `daily` | `run_date`, `date`, `file`, `device`, `pic`, `total` |
| `issues` | `run_date`, `file`, `sheet`, `device`, `row`, `case_no`, `scope`, `status`, `result`, `test_date`, `pic`, `ticket_id`, `note` |

Nếu vùng đích là một **Excel Table** thật (Insert → Table) bắt đầu đúng ở `header_row`,
app dùng luôn table đó, nên định dạng và công thức tự giãn theo dòng mới.

Sheet nào lọt vào Issues là do taxonomy quyết định: status có `"issue": true` trong
`parser/result_status.json` (mặc định là NG, Pending, Cancel).

## Nhóm Scope (Summary tách bảng)

Định nghĩa trong `parser/scope_groups.json`. Tab Summary vẽ **một bảng cho mỗi nhóm**, vì
phần việc FPT và phần việc JP là hai cam kết khác nhau — cộng chung lại không trả lời được
câu hỏi nào.

```json
{
  "groups": [
    {"key": "FPT", "label": "FPT", "match": ["FPT", "FPT (JM Support)"]},
    {"key": "JP",  "label": "JP",  "match": ["JP"]}
  ],
  "fallback": {"key": "Other", "label": "Other"}
}
```

| Key | Ý nghĩa |
|-----|---------|
| `groups[].key` | Tên nhóm (dùng nội bộ, và là giá trị cột `scope` trong `/api/summary`) |
| `groups[].label` | Tiêu đề hiển thị trên bảng |
| `groups[].match` | Các giá trị Scope thuộc nhóm này (không phân biệt hoa thường, tự cắt khoảng trắng) |
| `fallback` | **Bắt buộc.** Nhóm hứng mọi Scope không khớp — kể cả ô Scope trống |

`fallback` luôn đứng cuối. Scope gõ sai, Scope chưa cấu hình, hay dòng tiêu đề nhóm trong
file Excel (không có Scope) đều rơi vào đây, nên **tổng các bảng luôn bằng đúng số case đã
load** — không có case nào âm thầm biến mất. Bảng nào không có case thì tự ẩn.

Đổi env `SCOPE_GROUPS_CONFIG` để trỏ sang file khác, giống `RESULT_STATUS_CONFIG`.

Báo cáo SharePoint **không** đổi: `summary_rows` chỉ tách theo scope khi được gọi với
`by_scope=True` (chỉ `/api/summary` làm vậy). Sheet Summary trong báo cáo vẫn là một dòng cho
mỗi (file, device), nên không phải thêm cột nào trên SharePoint.

## Tab Detail: chỉ hiển thị case cần xử lý

Detail **chỉ nạp** các case có status đánh dấu `"review": true` — mặc định là NG, NG-OK,
Pending, Cancel. Case OK, NYS và Out Of Scope không xuất hiện ở đây: Detail là danh sách việc
còn tồn, không phải nơi tra cứu toàn bộ.

Vì vậy thẻ đầu tiên ở dải thống kê tên là **"To review"** chứ không phải "Total" — nó đếm số
case trên màn hình này, khác với `Total` ở tab Summary (đếm toàn bộ case trong phạm vi).

Bộ lọc **Result** là một dãy nút bật/tắt, **chọn được nhiều status cùng lúc** (ví dụ NG +
Pending). Không bật nút nào = xem tất cả. Mỗi status đang bật hiện thành một chip riêng, tắt
được từng cái. Bộ lọc này lọc theo **status** chứ không theo chữ trong ô Result, nên `保留`
và `Pending` là một.

## Test

```bash
python -m pytest -q
```
