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
│   ├── models.py           # SheetConfig, TestCase, CASE_COLUMNS (dataclass)
│   ├── status.py           # StatusSet: result -> status
│   ├── result_status.json  # cấu hình phân loại kết quả
│   ├── scope.py            # ScopeSet: Scope -> nhóm bảng Summary
│   ├── scope_groups.json   # cấu hình nhóm Scope (Summary tách bảng)
│   ├── device.py           # DeviceSet: tên device -> dòng device
│   ├── device_groups.json  # cấu hình gộp device (iPhone Min/Max -> iPhone)
│   ├── excel_reader.py     # đọc TOOL_DATA + test case từ .xlsx
│   ├── sheet_labels.py     # SheetLabels: nhãn cột mà dò layout tìm
│   ├── sheet_labels.json   # cấu hình nhãn ("結果", "確認日", "Pad"/"Phone"…)
│   └── tool_data_builder.py # dò layout của sheet -> các dòng TOOL_DATA
├── prepare/                # nơi duy nhất ghi vào chính file nguồn
│   ├── workbook.py         # đọc sheet / kiểm tra có TOOL_DATA chưa
│   ├── tool_data.py        # tạo, ghi và so sánh (diff) sheet TOOL_DATA
│   ├── clear.py            # lập kế hoạch & xoá ô kết quả của vòng test cũ
│   └── runner.py           # chạy 2 thao tác trên nhiều file, lỗi tính theo file
├── tools/
│   ├── generate_samples.py   # sinh file .xlsx mẫu
│   └── sample_config.json    # config mặc định cho generator
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
│   ├── test_api_prepare.py
│   ├── test_prepare_clear.py
│   ├── test_prepare_tool_data.py
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

## Chuẩn bị file (Prepare the workbooks)

File test case thật thường **chưa có** sheet `TOOL_DATA` — nên lần đầu nạp, app báo lỗi
`Sheet 'TOOL_DATA' not found` cho đúng những file đó. Mở **Setup → Prepare the workbooks**
để xử lý ngay trong app, không cần dòng lệnh.

Mỗi file đã nạp là một dòng, kèm nút theo trạng thái của nó:

| Nút | Khi nào hiện | Làm gì |
|-----|--------------|--------|
| **Create TOOL_DATA** | file chưa có sheet `TOOL_DATA` | Dò layout từ chính tiêu đề của sheet (`No.`, `担当者`, `結果`, ô ghi `Pad`/`Phone`…) rồi ghi sheet `TOOL_DATA` vào file |
| **Check TOOL_DATA** | file đã có sheet `TOOL_DATA` | Dò lại rồi **so sánh** với sheet đang có: cột nào đổi, block nào thừa/thiếu |
| **Clear results** | file đã có sheet `TOOL_DATA` | Xoá 5 ô kết quả (kết quả / ngày confirm / người confirm / ticket / note) để bắt đầu vòng test mới |

Hai điều quan trọng:

- **Không có gì bị ghi khi bấm một lần.** Mọi nút chỉ hiện *dự định*: dò được gì, sẽ xoá
  bao nhiêu dòng. Phải bấm **Apply** lần nữa mới thực sự ghi vào file — ô đã xoá thì không
  lấy lại được từ file.
- **Sheet `TOOL_DATA` đã có sẽ được so sánh, không mặc định ghi đè.** Nếu ai đó đã sửa tay
  cho đúng, đó mới là bản chuẩn của file đó; app chỉ đề nghị Apply khi thật sự có khác biệt.

Ô **Keep these results when clearing** chọn status nào được giữ lại qua vòng sau (mặc định
`Cancel`). Danh sách này sinh từ [parser/result_status.json](parser/result_status.json), nên
thêm status mới là nó tự hiện ra.

Nhãn mà bước dò layout tìm nằm ở [parser/sheet_labels.json](parser/sheet_labels.json) — sheet
của team bạn ghi `Status` thay vì `結果` thì sửa file đó, không sửa code.

## API

| Method | Endpoint       | Mô tả |
|--------|----------------|-------|
| POST   | `/api/load`    | Body `{"folder": "..."}` hoặc `{"files": ["...", "..."]}` |
| POST   | `/api/reload`  | Nạp lại từ source đã load trước đó |
| POST   | `/api/browse`  | Mở hộp thoại chọn folder/file của hệ điều hành, trả `{paths}` |
| GET    | `/api/data`    | Toàn bộ test case, kèm `status` đã phân loại |
| GET    | `/api/statuses`| Danh sách status (key / label / badge / text) + `needs_reason` + `executed` + `issue` |
| GET    | `/api/summary` | Gộp theo (nhóm Scope, file, device) + danh sách nhóm Scope + danh sách case thiếu lý do |
| GET    | `/api/daily`   | Gộp theo (file, device, PIC, date) |
| GET    | `/api/productivity` | Năng suất từng PIC: số case đã thực hiện / số ngày có làm việc |
| GET    | `/api/prepare/files` | Các file của source đang nạp: đã có `TOOL_DATA` chưa, mấy block |
| POST   | `/api/prepare/tool-data` | Body `{"files": [...], "apply": false}` — dò layout, ghi khi `apply` |
| POST   | `/api/prepare/clear` | Body `{"files": [...], "keep": [...], "apply": false}` — xoá ô kết quả |
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
| `fallback` | **Bắt buộc.** Nhóm hứng mọi Scope có giá trị nhưng không khớp nhóm nào |

`fallback` luôn đứng cuối. Scope gõ sai hay Scope chưa cấu hình rơi vào đây, nên **tổng các
bảng luôn bằng đúng số case đã load** — không có case nào âm thầm biến mất. Bảng nào không có
case thì tự ẩn.

**Ô Scope trống thì không phải là case.** Dòng tiêu đề nhóm trong file Excel, dòng trống, hay
phần dư ở cuối một block `start_row`–`end_row` đều không có Scope — trình đọc bỏ qua ngay từ
đầu, nên chúng không vào `Other` mà cũng không vào bất kỳ tab nào (Summary, Daily, Detail,
productivity, báo cáo SharePoint). Số case mỗi file mà ngăn setup hiển thị cũng đã trừ chúng
ra. Nói cách khác: **muốn một dòng được tính, dòng đó phải có Scope.**

Đổi env `SCOPE_GROUPS_CONFIG` để trỏ sang file khác, giống `RESULT_STATUS_CONFIG`.

Báo cáo SharePoint **không** đổi: `summary_rows` chỉ tách theo scope khi được gọi với
`by_scope=True` (chỉ `/api/summary` làm vậy). Sheet Summary trong báo cáo vẫn là một dòng cho
mỗi (file, device), nên không phải thêm cột nào trên SharePoint.

## Nhóm device (Summary gộp dòng theo loại máy)

Định nghĩa trong `parser/device_groups.json`. Một bộ test thường chạy cùng một máy ở hai cỡ
màn hình — `iPhone Min size` và `iPhone Max size` là hai block device trong file Excel, nhưng
với người đọc tổng số thì chỉ là một chiếc iPhone. Nút **Rows** trên tab Summary có ba trạng
thái: `Split` (một dòng cho mỗi file + device), `By device type` (gộp theo cấu hình này) và
`Combined` (một dòng cho mỗi file).

```json
{
  "families": [
    {"key": "iPhone", "label": "iPhone", "match": ["iPhone"]},
    {"key": "iPad",   "label": "iPad",   "match": ["iPad"]}
  ]
}
```

| Key | Ý nghĩa |
|-----|---------|
| `families[].key` | Tên nhóm (là giá trị cột `device_family` trong `/api/summary`) |
| `families[].label` | Tên hiển thị ở ô Device khi các dòng đã gộp |
| `families[].match` | Các chuỗi **nằm trong** tên device thì thuộc nhóm này (không phân biệt hoa thường) |

Khác với nhóm Scope ở hai điểm, và cả hai đều do bản chất của tên device mà ra:

- **Khớp theo chuỗi con, không phải cả ô.** Tên device viết tự do, có cả model lẫn cỡ màn hình,
  nên không ai liệt kê hết được. Vì vậy **thứ tự có ý nghĩa**: nhóm đầu tiên có chữ khớp sẽ
  thắng, nên đặt `iPad mini` **trên** `iPad` là một cấu hình có nghĩa. Nếu một chữ không bao giờ
  khớp được (ví dụ `Phone` đứng trên `iPhone`), app **từ chối lưu** thay vì im lặng bỏ qua.
- **Không có `fallback`.** Device không thuộc nhóm nào thì tự nó là một nhóm, giữ nguyên tên của
  mình. Nhờ vậy bảng sau khi gộp vẫn **bằng đúng tổng của bảng Split** — không giấu gì cả, và
  cũng không dồn một máy Android với một máy Windows vào chung một dòng.

Sửa được ngay trong tab **Config** (thẻ "Device families"), lưu là áp dụng luôn, không cần khởi
động lại. Hoặc đổi env `DEVICE_GROUPS_CONFIG` để trỏ sang file khác.

Báo cáo SharePoint **không** đổi: việc gộp chỉ xảy ra trên màn hình. `summary_rows` vẫn trả một
dòng cho mỗi (file, device); nó chỉ gắn thêm `device_family` vào mỗi dòng để màn hình và báo cáo
không thể hiểu khác nhau về chuyện device nào là máy nào.

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
