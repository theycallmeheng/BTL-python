from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Enum

db = SQLAlchemy()

# =========================
# Users (đăng nhập) + quyền
# =========================
class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    # NEW: vai trò & kho được phân (nếu staff)
    role = db.Column(Enum('admin', 'staff', name='user_role'), nullable=False, default='staff')
    assigned_kho = db.Column(db.String(50), db.ForeignKey('kho.id_kho'), nullable=True)

    kho = db.relationship('Kho', foreign_keys=[assigned_kho])

    # helpers
    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    @property
    def is_staff(self) -> bool:
        return self.role == 'staff'

    def allowed_khos(self):
        """Danh sách id_kho mà user được thao tác (dùng cho lọc query)."""
        if self.is_admin:
            return None  # None = tất cả
        return [self.assigned_kho] if self.assigned_kho else []

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


# =========================
# Các bảng danh mục/phụ trợ
# =========================
class DiaDiem(db.Model):
    __tablename__ = 'dia_diem'
    id_dia_diem = db.Column(db.String(100), primary_key=True)
    ten_dia_diem = db.Column(db.String(255), nullable=False)


class ChucVu(db.Model):
    __tablename__ = 'chuc_vu'
    id_chuc_vu = db.Column(db.String(100), primary_key=True)
    ten_chuc_vu = db.Column(db.String(255), nullable=False)
    luong_co_ban = db.Column(db.Numeric(15, 2), nullable=False)


class KhachHang(db.Model):
    __tablename__ = 'khach_hang'
    id_khach_hang = db.Column(db.String(100), primary_key=True)
    ho = db.Column(db.String(100))
    ten_dem = db.Column(db.String(100))
    ten = db.Column(db.String(100))
    so_dien_thoai = db.Column(db.String(20))
    id_dia_chi = db.Column(db.String(100), db.ForeignKey('dia_diem.id_dia_diem'))
    dia_diem = db.relationship("DiaDiem")

class NhaCungCap(db.Model):
    __tablename__ = 'nha_cung_cap'
    id_nha_cung_cap = db.Column(db.String(100), primary_key=True)
    ten_nha_cung_cap = db.Column(db.String(255), nullable=False)
    so_dien_thoai_nha_cung_cap = db.Column(db.String(20))
    id_dia_chi = db.Column(db.String(100), db.ForeignKey('dia_diem.id_dia_diem'))
    dia_diem = db.relationship("DiaDiem")

class XeVanChuyen(db.Model):
    __tablename__ = 'xe_van_chuyen'
    id_xe_van_chuyen = db.Column(db.String(100), primary_key=True)
    bien_so = db.Column(db.String(100), nullable=False)
    ho = db.Column(db.String(100))
    ten_dem = db.Column(db.String(100))
    ten = db.Column(db.String(100))
    so_dien_thoai_tai_xe = db.Column(db.String(20))


class NhanVien(db.Model):
    __tablename__ = 'nhan_vien'
    id_nhan_vien = db.Column(db.String(100), primary_key=True)
    ho = db.Column(db.String(100))
    ten_dem = db.Column(db.String(100))
    ten = db.Column(db.String(100))
    ngay_sinh = db.Column(db.Date)
    so_dien_thoai_nhan_vien = db.Column(db.String(20))
    id_chuc_vu = db.Column(db.String(100), db.ForeignKey('chuc_vu.id_chuc_vu'))


# ==============
# ĐA KHO & SẢN PHẨM
# ==============
class Kho(db.Model):
    __tablename__ = 'kho'
    id_kho = db.Column(db.String(50), primary_key=True)
    ten_kho = db.Column(db.String(255), nullable=False)
    id_dia_diem = db.Column(db.String(100), db.ForeignKey('dia_diem.id_dia_diem'))


class SanPham(db.Model):
    __tablename__ = 'san_pham'
    id_san_pham = db.Column(db.String(100), primary_key=True)
    ten_san_pham = db.Column(db.String(255), nullable=False)
    chat_lieu = db.Column(db.String(100))
    mau = db.Column(db.String(100))


class TonKho(db.Model):
    __tablename__ = 'ton_kho'
    id_kho = db.Column(db.String(50), db.ForeignKey('kho.id_kho'), primary_key=True)
    id_san_pham = db.Column(db.String(100), db.ForeignKey('san_pham.id_san_pham'), primary_key=True)
    so_luong = db.Column(db.Integer, nullable=False, default=0)
    nguong_canh_bao = db.Column(db.Integer, nullable=False, default=10)


# =========================
# Hóa đơn nhập / xuất
# =========================
class HoaDonNhap(db.Model):
    __tablename__ = 'hoa_don_nhap'
    # composite PK: (id_hoa_don_nhap, id_san_pham, id_kho)
    id_hoa_don_nhap = db.Column(db.String(100), primary_key=True)
    id_san_pham     = db.Column(db.String(100), db.ForeignKey('san_pham.id_san_pham'), primary_key=True)
    id_kho          = db.Column(db.String(50), db.ForeignKey('kho.id_kho'), primary_key=True)

    so_san_pham_nhap = db.Column(db.Integer, nullable=False)
    gia_nhap         = db.Column(db.Numeric(15, 2), nullable=False)
    ngay_nhap        = db.Column(db.DateTime, nullable=False)

    id_nhan_vien     = db.Column(db.String(100), db.ForeignKey('nhan_vien.id_nhan_vien'))
    id_nha_cung_cap  = db.Column(db.String(100), db.ForeignKey('nha_cung_cap.id_nha_cung_cap'))

    __table_args__ = (
        db.Index('ix_hdn_sp', 'id_san_pham'),
        db.Index('ix_hdn_kho', 'id_kho'),
        db.Index('ix_hdn_ngay', 'ngay_nhap'),
    )


class HoaDonXuat(db.Model):
    __tablename__ = 'hoa_don_xuat'
    # composite PK: (id_hoa_don_xuat, id_san_pham, id_kho)
    id_hoa_don_xuat = db.Column(db.String(100), primary_key=True)
    id_san_pham     = db.Column(db.String(100), db.ForeignKey('san_pham.id_san_pham'), primary_key=True)
    id_kho          = db.Column(db.String(50), db.ForeignKey('kho.id_kho'), primary_key=True)

    so_san_pham_xuat = db.Column(db.Integer, nullable=False)
    gia_ban          = db.Column(db.Numeric(15, 2), nullable=False)
    ngay_xuat        = db.Column(db.DateTime, nullable=False)

    id_nhan_vien     = db.Column(db.String(100), db.ForeignKey('nhan_vien.id_nhan_vien'))
    id_xe_van_chuyen = db.Column(db.String(100), db.ForeignKey('xe_van_chuyen.id_xe_van_chuyen'))
    id_khach_hang    = db.Column(db.String(100), db.ForeignKey('khach_hang.id_khach_hang'))

    __table_args__ = (
        db.Index('ix_hdx_sp', 'id_san_pham'),
        db.Index('ix_hdx_kho', 'id_kho'),
        db.Index('ix_hdx_ngay', 'ngay_xuat'),
    )


# =========================
# Điều chuyển nội bộ
# =========================
class DieuChuyen(db.Model):
    __tablename__ = 'dieu_chuyen'
    id_dieu_chuyen = db.Column(db.String(100), primary_key=True)
    kho_nguon = db.Column(db.String(50), db.ForeignKey('kho.id_kho'), nullable=False)
    kho_dich  = db.Column(db.String(50), db.ForeignKey('kho.id_kho'), nullable=False)
    ngay_dc   = db.Column(db.DateTime, nullable=False)
    ghi_chu   = db.Column(db.String(255))

    __table_args__ = (
        db.Index('ix_dc_ngay', 'ngay_dc'),
        db.Index('ix_dc_kho', 'kho_nguon', 'kho_dich'),
    )


class DieuChuyenCT(db.Model):
    __tablename__ = 'dieu_chuyen_ct'
    # composite PK: (id_dieu_chuyen, id_san_pham)
    id_dieu_chuyen = db.Column(db.String(100), db.ForeignKey('dieu_chuyen.id_dieu_chuyen'), primary_key=True)
    id_san_pham    = db.Column(db.String(100), db.ForeignKey('san_pham.id_san_pham'), primary_key=True)
    so_luong       = db.Column(db.Integer, nullable=False)
