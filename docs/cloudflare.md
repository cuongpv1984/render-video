# Triển khai Frame Studio lên Cloudflare

## Frontend Pages

Frontend trong bản này là Next.js static export, build tạo HTML/CSS/JS. Dữ liệu chế độ thử chỉ nằm ở browser. API production cấu hình trong màn hình Cài đặt, token owner không được nhúng vào build hoặc GitHub.

### Kết nối GitHub trên dashboard

1. Workers & Pages → Create application → Pages → Import an existing Git repository.
2. Chọn `cuongpv1984/render-video`, branch `main`.
3. Root directory để trống (root repo), framework preset None.
4. Build command `npm run build`; output directory `apps/web/out`.
5. Build environment `NODE_VERSION=24`.
6. Deploy; kiểm tra URL thật mà Cloudflare trả. Tên project đề xuất `render-video`, nhưng không giả định subdomain nếu tên đã được dùng.

### CLI

```sh
npm ci
npm run build
npm exec --workspace apps/web -- wrangler login
npm exec --workspace apps/web -- wrangler pages project create render-video --production-branch main --force
npm run deploy
```

Hoặc chạy workflow `Deploy Cloudflare web` khi đã cấu hình GitHub Secrets `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (token scope đúng account, Cloudflare Pages Edit). Token không gửi qua chat hay commit repo. Nếu dùng GitHub import trên Cloudflare, không cần token deployment trong GitHub.

Wrangler 4.151.0 có thể chuyển việc tạo project mới sang Workers. `--force` trong lệnh tạo project ở trên giữ việc tạo trên Pages trực tiếp; chỉ dùng cho lần tạo đầu. Các lệnh deploy sau đó không cần `--force`. Project render-video hiện đã được tạo và bản web chạy tại https://render-video.pages.dev/.

## Backend Containers

Cloudflare Pages không chạy container FFmpeg. API và worker dùng Cloudflare Containers, tối đa một instance trong pilot. Cần Workers Paid/Containers ở tài khoản và Docker để build image. Không bật gói trả phí trước khi chủ account quyết định.

1. Tạo PostgreSQL managed (ví dụ Neon/Supabase hoặc cloud đã có), UTF-8, TLS, backup/PITR. Chạy `db/001_app.sql` bằng migration account. Tạo app role riêng không superuser; quyền bảng tối thiểu theo nghiệp vụ.
2. Tạo bucket R2 private `frame-studio-exports`, credentials scope bucket này. Object exports không public.
3. Đặt `WEB_ORIGIN` đúng origin Pages được cấp; không có slash cuối. Đặt `R2_BUCKET` đúng tên bucket.
4. Trong `infra/cloudflare`, cài deps và `wrangler secret put` lần lượt DATABASE_URL, STUDIO_OWNER_TOKEN, R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY. Lệnh sẽ yêu cầu nhập secret trong terminal, không đưa secret vào command line.
5. Deploy container Worker từ config: `npm run deploy` ở thư mục `infra/cloudflare`. Dockerfile context repo root đã khai báo.
6. Kiểm API health/ready với token. Container phải đã provision trước khi endpoint phục vụ; startup có thể mất thời gian.
7. Cài đặt trong web: nhập API URL và token; chọn route Ảnh có chuyển động cho mọi cảnh, sync, quote backend và dựng MP4.

Nếu Containers chưa khả dụng, có thể chạy cùng Dockerfile trên container cloud khác rồi đặt API URL; giao diện vẫn trên Cloudflare. Đây là phương án thay thế, không tự đổi nhà cung cấp triển khai khi chưa thống nhất.

## Vận hành

Không lưu PostgreSQL trong ephemeral container. R2 bắt buộc với config Worker production. Worker gateway xác thực trước khi đánh thức container để giảm chi phí truy cập không hợp lệ. Thiết lập Cloudflare Access/rate limits, billing alerts, R2 lifecycle và retention trước public backend.

Console/API không ghi token hoặc DB URL. `WEB_ORIGIN` chỉ là CORS, không thay auth. Owner token pilot không dành cho public multiuser; cần triển khai OIDC/RLS để mở rộng.

Nguồn chính thức: [Cloudflare static Next.js](https://developers.cloudflare.com/pages/framework-guides/nextjs/deploy-a-static-nextjs-site/), [Containers get started](https://developers.cloudflare.com/containers/get-started/), [Containers environment variables](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/). Kiểm lại phiên bản Wrangler và Containers SDK nếu nâng cấp; dependency lockfiles là nguồn phiên bản khi build.
