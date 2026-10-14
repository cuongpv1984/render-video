# Frame Studio

AI Animation Studio V1.1 Balanced Mode, triển khai đầu tiên cho một chủ workspace.

Ứng dụng Next.js gồm storyboard, chọn route từng cảnh, dự toán, ngân sách thử, review, sao lưu dự án và xuất WebM thực bằng Canvas. Backend FastAPI dùng PostgreSQL để giữ ngân sách atomically trên scope project và workspace, idempotency, outbox và worker FFmpeg xuất MP4. Cloudflare Pages phục vụ frontend; cấu hình Cloudflare Containers cho backend nằm trong `infra/cloudflare`.

## Trạng thái chức năng

| Phần | Có trong bản này |
|---|---|
| Giao diện studio | Tạo dự án, thêm/sửa/xóa cảnh, duyệt storyboard, ratio, route, dự toán minh họa |
| Lưu local | localStorage; sao lưu/khôi phục JSON; mỗi trình duyệt có dữ liệu riêng |
| Xuất WebM | Video thật từ hình mẫu và camera, có phụ đề, không audio |
| Backend | Token owner, lưu dự án, quote, giữ tiền PostgreSQL, outbox, worker, ledger, cancel, download |
| Xuất MP4 backend | Renderer xác định, hình mẫu có sẵn, phụ đề, không audio |
| AI video / TTS / ảnh riêng | Chưa có adapter tài khoản production; không gọi provider có phí |
| Multi-tenant / OIDC / thư viện nhân vật | Có trong đặc tả, chưa triển khai trong owner pilot |

Giá video AI trong giao diện chỉ minh họa. Backend từ chối chạy AI khi provider chưa cấu hình. Biểu phí render backend là quota kế toán nội bộ theo mỗi cảnh, không phải số tiền thực trên hóa đơn cloud. Frontend thử không chi tiền thật và giải phóng toàn bộ khoản giữ giả lập khi kết thúc. Không dùng ledger phía trình duyệt để cấp quyền tiêu tiền thật.

## Chạy frontend

Node.js 22 trở lên, khuyến nghị 24:

```sh
npm ci
npm run dev
```

Mở `http://127.0.0.1:3000`. Dự án Mây được nạp làm mẫu. Duyệt dự toán → thử chạy → chọn hình mỗi cảnh → xuất hoạt cảnh. Để dự án trống, dùng nút tạo dự án.

## Chạy backend bằng Docker

```sh
cp .env.example .env
# Điền POSTGRES_PASSWORD và STUDIO_OWNER_TOKEN bằng giá trị ngẫu nhiên riêng.
docker compose up --build
```

API local ở `http://127.0.0.1:8000`, OpenAPI ở `/docs`. Trong Cài đặt frontend, nhập API và token, đồng bộ dự án rồi dự toán backend. Chọn route “Ảnh có chuyển động” cho mọi cảnh để worker xuất MP4 thật. Backend không giả làm video AI nếu route yêu cầu provider.

Database dùng schema runtime `db/001_app.sql`. `db/reference-schema.sql` là schema kiến trúc V1.1 đầy đủ dành cho phát triển tiếp, không chạy chồng vào app runtime. Backend pilot dùng 1 owner token, cần thêm OIDC và tenant isolation trước khi mở dịch vụ nhiều người dùng.

## Chạy Python trực tiếp

```sh
python -m venv .venv
# Kích hoạt venv theo hệ điều hành.
pip install -r services/api/requirements.txt
export PYTHONPATH=services/api
export DATABASE_URL='postgresql://user:password@localhost/studio'
export STUDIO_OWNER_TOKEN='your-random-token-at-least-32-characters'
python -m app.migrate
python -m app.serve
```

Cần FFmpeg và FFprobe có libass và fonts tiếng Việt. `DATA_DIR` mặc định `data`. Production Containers bắt buộc PostgreSQL bên ngoài và bucket R2 private vì filesystem container không phải storage bền vững.

## Kiểm thử

```sh
npm run typecheck
npm test
npm run build
PYTHONPATH=services/api DATABASE_URL='postgresql://.../studio_test' WORKSPACE_BUDGET_MICRO_USD=20000 python -m pytest services/api/tests -q
```

Chỉ dùng database test: fixture sẽ truncate các bảng `app_*`. Suite bao gồm race 50 requests, idempotency đồng thời, stale/expired quote, thiếu provider không giữ tiền, settle một lần, actual overrun, cancel không release sớm, auth, schema tham chiếu, expired lease và xuất MP4 nếu có FFmpeg. CI cung cấp PostgreSQL 17 và FFmpeg. Test runner PostgreSQL nhúng cục bộ có trong `scripts/test-postgres.mjs`; có thể đặt `PYTHON_EXECUTABLE` khi Python nằm ở đường dẫn riêng.

## Đưa lên Cloudflare

Hướng dẫn đầy đủ: [Cloudflare deployment](docs/cloudflare.md). Frontend build ra `apps/web/out`, không yêu cầu Next.js server; do đó Pages static phù hợp cho bản này. Backend được đóng gói Linux container riêng, không cố chạy FFmpeg trong Pages.

## Tài liệu

- [Đặc tả V1.1](docs/specification.md)
- [Quyết định triển khai pilot](docs/implementation.md)
- [Cloudflare và vận hành](docs/cloudflare.md)

Các release cần hoàn thiện tiếp theo: đăng nhập OIDC đa workspace, provider catalog với giá xác minh, adapter video/TTS, upload reference R2, storyboard AI, retry sáng tạo và QC identity. Không bật paid auto-route trước khi kiểm chứng billing bounds và khả năng tra cứu request mơ hồ.
