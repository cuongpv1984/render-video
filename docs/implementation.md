# Quyết định triển khai phiên bản đầu

Baseline 14 tháng 10 năm 2026. Repo trước khi triển khai trống. Bản này xây dựng một lát cắt hoạt động được của đặc tả; không tuyên bố toàn bộ lộ trình 8 tuần đã hoàn tất.

## Các quyết định

Next.js App Router static export lên Cloudflare Pages. Client không có provider secrets; chế độ thử hoạt động ngay mà chưa cần tài khoản AI. Artwork là SVG gốc kèm PNG dành cho FFmpeg. WebM xuất từ Canvas, có phụ đề, không audio. Không gọi AI để tạo demo assets nên không phát sinh phí AI.

FastAPI owner pilot dùng token tối thiểu 32 ký tự. PostgreSQL authoritative cho backend, lưu snapshot quote/run và ledger. Mỗi run reserve full ceiling trên account project và account workspace theo tháng UTC. Lock order project → account id sorted → run. Transaction accept ghi outbox cùng hold. Worker claim bằng FOR UPDATE SKIP LOCKED. Callback provider không có ở bản này vì chưa có paid adapter.

Các scene AI được quote minh họa và đánh dấu dispatch_ready=false. Accept sẽ trả PROVIDER_NOT_CONFIGURED trước khi tạo hold. Các scene renderer xác định dùng biểu phí nội bộ RENDER_TARIFF_MICRO_USD mỗi cảnh; thành công mới quyết toán, lỗi/hủy charge 0. Chi phí cloud thực vẫn theo hóa đơn nhà cung cấp, cần thêm cost ingestion để theo dõi. Cấu hình period/account stop được kiểm ở lúc accept; worker chỉ dispatch trong kỳ UTC hiện tại. Account reservation kỳ cũ không chuyển tự động; worker cancel và release khi xác nhận chưa render.

Worker lease hết hạn giữ tiền và chuyển needs_reconciliation. Không tự release do TTL. V1 pilot chỉ một worker container, tối đa một render đồng thời. Muốn nhiều worker cần lease fencing và claim ownership token để worker cũ không settle sau takeover. Container sleeping/restart không mất ledger/outbox ở PostgreSQL; tác vụ đang render cần đối soát riêng.

Object exports production lưu R2 private. API download trả signed URL 5 phút. Local mode dùng volume thư mục data. Object key dựa trên run UUID, không nhận path từ client. Renderer truyền arguments dưới dạng list, chỉ nhận tên artwork trong allowlist và script có giới hạn.

## Những phần cần trước production nhiều người dùng

OIDC, membership, RLS tenant, rate limits, quotas upload/download/retention, R2 lifecycle và billing alerts, provider adapter/callback với price-bound được xác nhận, retry counters, quality benchmark và migration versioning Alembic. Runtime schema hiện dùng migration nền idempotent, không tự nâng schema ứng dụng đang chạy.

Owner pilot không có khả năng chỉnh hạn mức backend trong UI. WORKSPACE_BUDGET_MICRO_USD chỉ khởi tạo kỳ mới; đổi cấu hình không sửa account đã tồn tại. Muốn đổi account hiện tại cần một admin transaction có ledger ADJUST_LIMIT, kiểm spent+held và audit. Endpoint dự án có thể tăng/giảm budget project sau khi kiểm account; chỉ owner token được phép.

## Đối soát

Tổng account phải khớp ledger SUM(spent_delta), SUM(held_delta), SUM(limit_delta). Nếu lệch, đặt stop_dispatch trước điều tra. Overrun actual được ghi đủ và stop scope. Với needs_reconciliation: xác nhận không còn process render trước khi quyết toán; kiểm output object hợp lệ nếu worker đã upload trước crash. Không đổi state/release hold chỉ để dọn dashboard.

## Release checklist

Web typecheck/tests/build; PostgreSQL integration và 50-way race; real MP4 smoke; responsive và chức năng cơ bản trong browser; secrets không được commit; CI pass. Cloudflare deploy cần phiên account đúng và scope deployment đã được người dùng cấp. Backend deploy cần Workers Paid/Containers, PostgreSQL durable và R2 credentials. Mã cấu hình không tự tạo một subscription hay nhập thông tin thanh toán.
