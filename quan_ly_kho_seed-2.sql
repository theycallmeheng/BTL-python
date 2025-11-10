-- ===========================================
-- DATABASE: QUAN_LY_KHO (đa kho + điều chuyển + kiểm kê + vai trò)
-- ===========================================
CREATE DATABASE IF NOT EXISTS quan_ly_kho
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE quan_ly_kho;

-- --------------------------
-- Reset bảng (nếu cần)
-- --------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS phieu_kiem_ke_ct;
DROP TABLE IF EXISTS phieu_kiem_ke;
DROP TABLE IF EXISTS dieu_chuyen_ct;
DROP TABLE IF EXISTS dieu_chuyen;
DROP TABLE IF EXISTS hoa_don_xuat;
DROP TABLE IF EXISTS hoa_don_nhap;
DROP TABLE IF EXISTS ton_kho;
DROP TABLE IF EXISTS san_pham;
DROP TABLE IF EXISTS nhan_vien;
DROP TABLE IF EXISTS xe_van_chuyen;
DROP TABLE IF EXISTS nha_cung_cap;
DROP TABLE IF EXISTS khach_hang;
DROP TABLE IF EXISTS chuc_vu;
DROP TABLE IF EXISTS dia_diem;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS kho;
SET FOREIGN_KEY_CHECKS = 1;

-- --------------------------
-- Danh mục địa điểm, chức vụ
-- --------------------------
CREATE TABLE dia_diem (
  id_dia_diem   VARCHAR(100) PRIMARY KEY,
  ten_dia_diem  VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE chuc_vu (
  id_chuc_vu    VARCHAR(100) PRIMARY KEY,
  ten_chuc_vu   VARCHAR(255) NOT NULL,
  luong_co_ban  DECIMAL(15,2) NOT NULL
) ENGINE=InnoDB;

-- --------------------------
-- Nhân viên, NCC, KH, xe VC
-- --------------------------
CREATE TABLE nhan_vien (
  id_nhan_vien            VARCHAR(100) PRIMARY KEY,
  ho                      VARCHAR(100),
  ten_dem                 VARCHAR(100),
  ten                     VARCHAR(100),
  ngay_sinh               DATE,
  so_dien_thoai_nhan_vien VARCHAR(20),
  id_chuc_vu              VARCHAR(100),
  CONSTRAINT fk_nv_cv FOREIGN KEY (id_chuc_vu)
    REFERENCES chuc_vu(id_chuc_vu)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE nha_cung_cap (
  id_nha_cung_cap            VARCHAR(100) PRIMARY KEY,
  ten_nha_cung_cap           VARCHAR(255) NOT NULL,
  so_dien_thoai_nha_cung_cap VARCHAR(20),
  id_dia_chi                 VARCHAR(100),
  CONSTRAINT fk_ncc_dd FOREIGN KEY (id_dia_chi)
    REFERENCES dia_diem(id_dia_diem)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE khach_hang (
  id_khach_hang  VARCHAR(100) PRIMARY KEY,
  ho             VARCHAR(100),
  ten_dem        VARCHAR(100),
  ten            VARCHAR(100),
  so_dien_thoai  VARCHAR(20),
  id_dia_chi     VARCHAR(100),
  CONSTRAINT fk_kh_dd FOREIGN KEY (id_dia_chi)
    REFERENCES dia_diem(id_dia_diem)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE xe_van_chuyen (
  id_xe_van_chuyen      VARCHAR(100) PRIMARY KEY,
  bien_so               VARCHAR(100) NOT NULL,
  ho                    VARCHAR(100),
  ten_dem               VARCHAR(100),
  ten                   VARCHAR(100),
  so_dien_thoai_tai_xe  VARCHAR(20)
) ENGINE=InnoDB;

-- --------------------------
-- Kho hàng
-- --------------------------
CREATE TABLE kho (
  id_kho      VARCHAR(50) PRIMARY KEY,
  ten_kho     VARCHAR(255) NOT NULL,
  id_dia_diem VARCHAR(100),
  CONSTRAINT fk_kho_dd FOREIGN KEY (id_dia_diem)
    REFERENCES dia_diem(id_dia_diem)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- --------------------------
-- Sản phẩm
-- --------------------------
CREATE TABLE san_pham (
  id_san_pham   VARCHAR(100) PRIMARY KEY,
  ten_san_pham  VARCHAR(255) NOT NULL,
  chat_lieu     VARCHAR(100),
  mau           VARCHAR(100)
) ENGINE=InnoDB;

-- --------------------------
-- Tồn kho nhanh
-- --------------------------
CREATE TABLE ton_kho (
  id_kho          VARCHAR(50) NOT NULL,
  id_san_pham     VARCHAR(100) NOT NULL,
  so_luong        INT NOT NULL DEFAULT 0,
  nguong_canh_bao INT NOT NULL DEFAULT 10,
  PRIMARY KEY (id_kho, id_san_pham),
  CONSTRAINT fk_tk_kho FOREIGN KEY (id_kho)
    REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_tk_sp FOREIGN KEY (id_san_pham)
    REFERENCES san_pham(id_san_pham)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- --------------------------
-- Hóa đơn nhập / xuất
-- --------------------------
CREATE TABLE hoa_don_nhap (
  id_hoa_don_nhap  VARCHAR(100) NOT NULL,
  id_san_pham      VARCHAR(100) NOT NULL,
  id_kho           VARCHAR(50)  NOT NULL,
  so_san_pham_nhap INT UNSIGNED NOT NULL,
  gia_nhap         DECIMAL(15,2) NOT NULL,
  ngay_nhap        DATETIME NOT NULL,
  id_nhan_vien     VARCHAR(100),
  id_nha_cung_cap  VARCHAR(100),
  PRIMARY KEY (id_hoa_don_nhap, id_san_pham, id_kho),
  CONSTRAINT fk_hdn_sp FOREIGN KEY (id_san_pham) REFERENCES san_pham(id_san_pham)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_hdn_kho FOREIGN KEY (id_kho) REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_hdn_nv FOREIGN KEY (id_nhan_vien) REFERENCES nhan_vien(id_nhan_vien)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_hdn_ncc FOREIGN KEY (id_nha_cung_cap) REFERENCES nha_cung_cap(id_nha_cung_cap)
    ON UPDATE CASCADE ON DELETE SET NULL,
  INDEX ix_hdn_sp (id_san_pham),
  INDEX ix_hdn_kho (id_kho),
  INDEX ix_hdn_ngay (ngay_nhap)
) ENGINE=InnoDB;

CREATE TABLE hoa_don_xuat (
  id_hoa_don_xuat  VARCHAR(100) NOT NULL,
  id_san_pham      VARCHAR(100) NOT NULL,
  id_kho           VARCHAR(50)  NOT NULL,
  so_san_pham_xuat INT UNSIGNED NOT NULL,
  gia_ban          DECIMAL(15,2) NOT NULL,
  ngay_xuat        DATETIME NOT NULL,
  id_nhan_vien     VARCHAR(100),
  id_xe_van_chuyen VARCHAR(100),
  id_khach_hang    VARCHAR(100),
  PRIMARY KEY (id_hoa_don_xuat, id_san_pham, id_kho),
  CONSTRAINT fk_hdx_sp FOREIGN KEY (id_san_pham) REFERENCES san_pham(id_san_pham)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_hdx_kho FOREIGN KEY (id_kho) REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_hdx_nv FOREIGN KEY (id_nhan_vien) REFERENCES nhan_vien(id_nhan_vien)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_hdx_xe FOREIGN KEY (id_xe_van_chuyen) REFERENCES xe_van_chuyen(id_xe_van_chuyen)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_hdx_kh FOREIGN KEY (id_khach_hang) REFERENCES khach_hang(id_khach_hang)
    ON UPDATE CASCADE ON DELETE SET NULL,
  INDEX ix_hdx_sp (id_san_pham),
  INDEX ix_hdx_kho (id_kho),
  INDEX ix_hdx_ngay (ngay_xuat)
) ENGINE=InnoDB;

-- --------------------------
-- Điều chuyển nội bộ
-- --------------------------
CREATE TABLE dieu_chuyen (
  id_dieu_chuyen VARCHAR(100) PRIMARY KEY,
  kho_nguon VARCHAR(50) NOT NULL,
  kho_dich  VARCHAR(50) NOT NULL,
  ngay_dc   DATETIME NOT NULL,
  ghi_chu   VARCHAR(255),
  CONSTRAINT fk_dc_kho_src FOREIGN KEY (kho_nguon) REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_dc_kho_dst FOREIGN KEY (kho_dich) REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE dieu_chuyen_ct (
  id_dieu_chuyen VARCHAR(100) NOT NULL,
  id_san_pham    VARCHAR(100) NOT NULL,
  so_luong       INT UNSIGNED NOT NULL,
  PRIMARY KEY (id_dieu_chuyen, id_san_pham),
  CONSTRAINT fk_dcct_hd FOREIGN KEY (id_dieu_chuyen) REFERENCES dieu_chuyen(id_dieu_chuyen)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_dcct_sp FOREIGN KEY (id_san_pham) REFERENCES san_pham(id_san_pham)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE INDEX ix_dc_ngay ON dieu_chuyen(ngay_dc);
CREATE INDEX ix_dc_kho  ON dieu_chuyen(kho_nguon, kho_dich);

-- --------------------------
-- KIỂM KÊ (MỚI)
-- --------------------------
CREATE TABLE phieu_kiem_ke (
  id_pkk   VARCHAR(100) PRIMARY KEY,
  id_kho   VARCHAR(50)  NOT NULL,
  ngay_kk  DATETIME     NOT NULL,
  nguoi_kk VARCHAR(80)  NOT NULL,
  ghi_chu  VARCHAR(255),
  CONSTRAINT fk_pkk_kho FOREIGN KEY (id_kho) REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE phieu_kiem_ke_ct (
  id_pkk       VARCHAR(100) NOT NULL,
  id_san_pham  VARCHAR(100) NOT NULL,
  so_he_thong  INT NOT NULL,
  so_thuc_te   INT NOT NULL,
  chenhlech    INT NOT NULL,
  PRIMARY KEY (id_pkk, id_san_pham),
  CONSTRAINT fk_pkkct_pkk FOREIGN KEY (id_pkk) REFERENCES phieu_kiem_ke(id_pkk)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_pkkct_sp  FOREIGN KEY (id_san_pham) REFERENCES san_pham(id_san_pham)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- --------------------------
-- Users (đăng nhập) + quyền
-- --------------------------
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(120),
  role ENUM('admin','staff') NOT NULL DEFAULT 'staff',
  assigned_kho VARCHAR(50) NULL,
  CONSTRAINT fk_users_kho FOREIGN KEY (assigned_kho)
    REFERENCES kho(id_kho)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- --------------------------
-- DỮ LIỆU MẪU (Seed)
-- --------------------------
INSERT INTO dia_diem VALUES
('DD001','Hà Nội'),
('DD002','Hải Phòng'),
('DD003','Đà Nẵng'),
('DD004','TP.HCM'),
('DD005','Cần Thơ');

INSERT INTO chuc_vu VALUES
('CV001','Quản lý kho',15000000.00),
('CV002','Nhân viên kho',9000000.00);

-- 3 nhân viên mẫu (NV003 thêm mới)
INSERT INTO nhan_vien VALUES
('NV001','Nguyễn','Văn','An','1992-03-10','0909000001','CV001'),
('NV002','Trần','Thị','Bình','1996-07-21','0909000002','CV002'),
('NV003','Lê','Văn','Cường','1995-05-09','0909000003','CV002');

INSERT INTO nha_cung_cap VALUES
('NCC001','Nhà cung cấp Sao Mai','0288888888','DD004'),
('NCC002','Nhà cung cấp Hồng Hà','0247777777','DD001');

INSERT INTO khach_hang VALUES
('KH001','Phạm','Minh','Tuấn','0909888777','DD001'),
('KH002','Lê','Thị','Hà','0909777666','DD004');

INSERT INTO xe_van_chuyen VALUES
('VC001','51A-123.45','Nguyễn','Văn','Tài','0912000001'),
('VC002','43B-678.90','Đỗ','Thành','Công','0912000002');

INSERT INTO kho VALUES
('K1','Kho Hà Nội','DD001'),
('K2','Kho TP.HCM','DD004'),
('K3','Kho Đà Nẵng','DD003');

INSERT INTO san_pham VALUES
('SP001','Bút bi Thiên Long 0.5','Nhựa','Xanh'),
('SP002','Vở học sinh 200 trang','Giấy','Trắng'),
('SP003','Kéo học sinh','Thép + Nhựa','Đen'),
('SP004','Thước kẻ 20cm','Nhựa','Trong suốt'),
('SP005','Tẩy chì Campus','Cao su','Trắng'),
('SP006','Bút chì 2B','Gỗ','Vàng'),
('SP007','Bút dạ quang Stabilo','Nhựa','Vàng neon'),
('SP008','Bìa hồ sơ A4','Nhựa','Xanh dương'),
('SP009','Tập giấy note 3x3','Giấy','Vàng nhạt'),
('SP010','Ghim bấm số 10','Thép','Bạc'),
('SP011','Máy tính Casio FX-580VN X','Nhựa','Đen'),
('SP012','Băng keo trong 5cm','Nhựa','Trong suốt'),
('SP013','Kẹp giấy cỡ nhỏ','Thép','Đen'),
('SP014','Bút lông bảng Thiên Long','Nhựa','Đỏ'),
('SP015','Sổ tay lò xo A5','Giấy','Xanh'),
('SP016','Giấy in A4 Double A','Giấy','Trắng'),
('SP017','Chuột máy tính Logitech','Nhựa','Đen'),
('SP018','Bàn phím không dây Logitech','Nhựa','Đen'),
('SP019','Ổ cắm điện 3 chấu','Nhựa','Trắng'),
('SP020','Bút xóa nước','Nhựa','Trắng');

-- Hóa đơn mẫu
INSERT INTO hoa_don_nhap VALUES
('N001','SP001','K1',200,3000.00,'2025-10-10 10:00:00','NV001','NCC001'),
('N002','SP002','K1',150,8000.00,'2025-10-10 10:05:00','NV001','NCC002'),
('N003','SP003','K2',100,12000.00,'2025-10-12 09:30:00','NV002','NCC001');

INSERT INTO hoa_don_xuat VALUES
('X001','SP001','K1',50,5000.00,'2025-10-13 14:00:00','NV002','VC001','KH001'),
('X002','SP002','K1',30,11000.00,'2025-10-13 14:05:00','NV002','VC001','KH001'),
('X003','SP003','K2',10,18000.00,'2025-10-14 09:45:00','NV001','VC002','KH002');

-- Tồn kho ban đầu
INSERT INTO ton_kho (id_kho, id_san_pham, so_luong, nguong_canh_bao) VALUES
('K1','SP001',150,10),('K1','SP002',120,10),('K1','SP003',80,10),
('K1','SP004',100,10),('K1','SP005',60,10),('K1','SP006',200,10),
('K1','SP007',90,10),('K1','SP008',70,10),('K1','SP009',50,10),('K1','SP010',110,10),

('K2','SP001',60,10),('K2','SP002',90,10),('K2','SP003',90,10),('K2','SP004',100,10),
('K2','SP005',80,10),('K2','SP006',140,10),('K2','SP007',60,10),('K2','SP008',50,10),
('K2','SP009',120,10),('K2','SP010',70,10),('K2','SP011',40,10),('K2','SP012',60,10),
('K2','SP013',90,10),('K2','SP014',80,10),('K2','SP015',100,10),

('K3','SP001',40,10),('K3','SP002',70,10),('K3','SP003',50,10),('K3','SP004',90,10),
('K3','SP005',60,10),('K3','SP006',80,10),('K3','SP007',70,10),('K3','SP008',90,10),
('K3','SP009',40,10),('K3','SP010',120,10),('K3','SP011',30,10),('K3','SP012',60,10),
('K3','SP013',50,10),('K3','SP014',70,10),('K3','SP015',100,10),('K3','SP016',150,10),
('K3','SP017',40,10),('K3','SP018',50,10),('K3','SP019',60,10),('K3','SP020',80,10);

-- Điều chuyển mẫu
INSERT INTO dieu_chuyen VALUES
('DC001','K1','K2','2025-10-20 10:00:00','Chuyển bút bi sang kho 2');
INSERT INTO dieu_chuyen_ct VALUES ('DC001','SP001',20);
UPDATE ton_kho SET so_luong = so_luong - 20 WHERE id_kho='K1' AND id_san_pham='SP001';
INSERT INTO ton_kho (id_kho,id_san_pham,so_luong,nguong_canh_bao)
VALUES ('K2','SP001',20,10)
ON DUPLICATE KEY UPDATE so_luong = so_luong + 20;

-- Xoá users để ứng dụng tự bootstrap
DELETE FROM users;

-- (TÙY CHỌN) Tạo nhanh user (cần password_hash do app sinh):
-- INSERT INTO users(username, password_hash, full_name, role, assigned_kho)
-- VALUES ('admin','<hash_pbkdf2_admin123>','Quản trị','admin',NULL),
--        ('nv_k1','<hash_pbkdf2_123456>','Nhân viên K1','staff','K1'),
--        ('nv_k2','<hash_pbkdf2_123456>','Nhân viên K2','staff','K2');
