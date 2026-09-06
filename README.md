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
│   └── index.html          # Bootstrap 5 UI, 3 tab: Summary / Daily / Detail
└── static/
    ├── css/style.css
    └── js/                 # ES modules, nạp qua <script type="module">
        ├── main.js         # entry point: wiring + chuyển tab
        ├── dom.js          # $, $$, esc
        ├── api.js          # mọi lời gọi fetch tới /api/*
        ├── sourcePanel.js  # chọn folder/file, Load & Reload, localStorage
        ├── reportPanel.js  # đăng nhập SharePoint + nút Publish
        ├── taxonomy.js     # status từ /api/statuses + scaffolding bảng
        ├── sorting.js      # sort theo cột (asc -> desc -> bỏ sort)
        ├── filters.js      # uniqueOf, populateSelect
        ├── pagination.js   # phân trang
        ├── charts.js       # Chart.js (doughnut + bar)
        └── views/
            ├── summary.js  # gộp theo file & device
            ├── daily.js    # tiến độ theo ngày
            └── detail.js   # stat card, filter, bảng, phân trang
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
| `sheets_per_file` | Số sheet test case trong mỗi file |
| `devices_per_sheet` | Số device trong mỗi sheet |
| `cases_per_sheet` | `{min, max}` — số test case mỗi sheet (random trong khoảng) |
| `pic_names` | Danh sách tên PIC |
| `seed` | Cố định seed để sinh lại y hệt (`null` = ngẫu nhiên) |
| `file_prefix`, `sheet_names`, `device_names` | Pool tên file / sheet / device |
| `scopes` | Giá trị cột Scope — mặc định `FPT`, `FPT (JM Support)`, `JP` |
| `result_weights` | Tỉ trọng các Result: `OK`, `NG`, `NG-OK`, `保留`, `対象外`, `""` (rỗng) |
| `missing_reason_rate` | Tỉ lệ dòng NG/NG-OK/保留/対象外 **thiếu** Ticket ID lẫn Note |
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
| GET    | `/api/summary` | Gộp theo (file, device) + danh sách case thiếu lý do |
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

Mỗi status gồm:

| Key | Ý nghĩa |
|-----|---------|
| `key` | Tên cột trong `/api/summary`, `/api/daily` |
| `label` | Nhãn hiển thị trên UI |
| `match` | Các giá trị Result ánh xạ vào status này (không phân biệt hoa thường) |
| `badge` | Class Bootstrap cho badge |
| `text` | Class Bootstrap cho màu chữ ở bảng Summary / Daily. Bỏ trống (`""`) = màu mặc định; không khai báo = suy ra từ `badge` |
| `empty` | Đúng 1 status đánh dấu `true` — dùng cho ô Result rỗng |
| `fallback` | Đúng 1 status đánh dấu `true` — nhận mọi giá trị lạ |
| `executed` | Đánh dấu `true` = coi như đã thực hiện; chỉ các status này được tính vào năng suất |
| `issue` | Đánh dấu `true` = cần theo dõi; đúng các status này lên bảng Issues của báo cáo SharePoint (mặc định NG, Pending, Cancel) |
| `needs_reason` | (cấp ngoài) Các status bắt buộc phải có Ticket ID hoặc Note |

Nhờ có `fallback`, giá trị lạ không bị bỏ sót: `total` của mỗi dòng luôn bằng tổng các
cột status.

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
  `summary` và `daily` (dòng `issues` là từng case, không phải nhóm đếm).
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

## Test

```bash
python -m pytest -q
```
