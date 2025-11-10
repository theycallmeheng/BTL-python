from datetime import datetime, timedelta
from io import StringIO
import csv

from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, cast
from sqlalchemy.sql.sqltypes import Date
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError

from config import Config
from models import (
    db,
    SanPham,
    HoaDonNhap,
    HoaDonXuat,
    TonKho,
    Kho,
    User,
    NhanVien,
    NhaCungCap,
    XeVanChuyen,
    KhachHang,
    DiaDiem,
    DieuChuyen,
    DieuChuyenCT,
)

# Map username -> mã nhân viên
USERNAME_TO_NV = {
    "nv1": "NV001",
    "nv2": "NV002",
    "nv3": "NV003",
}

# -----------------------------------------------------------------------------
# App & Auth init
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Vui lòng đăng nhập để tiếp tục."

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Bootstrap users table & default accounts (admin + 3 nhân viên)
with app.app_context():
    try:
        User.__table__.create(bind=db.engine, checkfirst=True)
    except Exception as e:
        print("Users table check/create error:", e)

    created = []

    def ensure_user(username, password, full_name, role, assigned_kho=None):
        uname = (username or "").strip().lower()
        if not uname:
            return
        u = User.query.filter_by(username=uname).first()
        if u:
            return
        u = User(
            username=uname,
            full_name=full_name,
            role=role,
            assigned_kho=assigned_kho
        )
        u.password_hash = generate_password_hash(password)
        db.session.add(u)
        created.append(uname)

    try:
        ensure_user("admin", "admin123", "Quản trị hệ thống", "admin", None)
        ensure_user("nv1", "123456", "Nhân viên Kho 1", "staff", "K1")
        ensure_user("nv2", "123456", "Nhân viên Kho 2", "staff", "K2")
        ensure_user("nv3", "123456", "Nhân viên Kho 3", "staff", "K3")

        if created:
            db.session.commit()
            print("✅ Đã bootstrap user:", ", ".join(created))
        else:
            print("ℹ️ User đã tồn tại, bỏ qua bootstrap.")
    except Exception as e:
        db.session.rollback()
        print("Bootstrap users error:", e)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def is_admin():
    return (getattr(current_user, "role", None) == "admin")

def is_staff():
    return (getattr(current_user, "role", None) == "staff")

def user_kho():
    if is_staff():
        return current_user.assigned_kho
    return None

def limit_khos_for_user():
    if is_admin():
        return Kho.query.order_by(Kho.id_kho).all()
    if current_user.is_authenticated and current_user.assigned_kho:
        return Kho.query.filter_by(id_kho=current_user.assigned_kho).all()
    return []

def enforce_staff_kho(selected_kho: str | None, allow_all: bool = False) -> str:
    if is_admin():
        return selected_kho if selected_kho else ("ALL" if allow_all else "")
    return current_user.assigned_kho or ""

def get_ton_kho_dict(id_kho=None):
    """Đọc nhanh tồn kho; nếu thiếu bảng TonKho thì fallback theo N-X."""
    try:
        q = db.session.query(TonKho.id_san_pham, func.sum(TonKho.so_luong))
        if id_kho and id_kho != "ALL":
            q = q.filter(TonKho.id_kho == id_kho)
        rows = q.group_by(TonKho.id_san_pham).all()
        return {k: int(v or 0) for k, v in rows}
    except (ProgrammingError, OperationalError):
        db.session.rollback()
        qn = db.session.query(HoaDonNhap.id_san_pham, func.sum(HoaDonNhap.so_san_pham_nhap))
        qx = db.session.query(HoaDonXuat.id_san_pham, func.sum(HoaDonXuat.so_san_pham_xuat))
        if id_kho and id_kho != "ALL" and hasattr(HoaDonNhap, "id_kho"):
            qn = qn.filter(HoaDonNhap.id_kho == id_kho)
        if id_kho and id_kho != "ALL" and hasattr(HoaDonXuat, "id_kho"):
            qx = qx.filter(HoaDonXuat.id_kho == id_kho)
        dn = {k: int(v or 0) for k, v in qn.group_by(HoaDonNhap.id_san_pham).all()}
        dx = {k: int(v or 0) for k, v in qx.group_by(HoaDonXuat.id_san_pham).all()}
        ids = set(dn) | set(dx)
        return {i: dn.get(i, 0) - dx.get(i, 0) for i in ids}

def _next_code_from_last(last_code: str | None, fallback_prefix: str) -> str:
    if last_code and last_code[0].isalpha():
        prefix = "".join([c for c in last_code if c.isalpha()]) or fallback_prefix
        number = "".join([c for c in last_code if c.isdigit()])
        return f"{prefix}{int(number) + 1:03d}" if number.isdigit() else f"{prefix}001"
    return f"{fallback_prefix}001"

def _upsert_ton_kho(id_kho, id_sp, delta, min_zero=True):
    tk = db.session.get(TonKho, {"id_kho": id_kho, "id_san_pham": id_sp})
    if not tk:
        tk = TonKho(id_kho=id_kho, id_san_pham=id_sp, so_luong=0, nguong_canh_bao=10)
        db.session.add(tk)
    tk.so_luong = (tk.so_luong or 0) + int(delta)
    if min_zero and tk.so_luong < 0:
        raise ValueError("Số lượng tồn không được âm")
    return tk.so_luong

@app.context_processor
def inject_role_helpers():
    return dict(IS_ADMIN=is_admin(), IS_STAFF=is_staff(), ASSIGNED_KHO=user_kho())

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
@login_required
def home():
    return redirect(url_for("home_page"))

# ---- Auth ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if u and check_password_hash(u.password_hash, request.form.get("password", "")):
            login_user(u)
            flash("Đăng nhập thành công!", "success")
            return redirect(url_for("home_page"))
        flash("Sai tài khoản hoặc mật khẩu", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Đã đăng xuất", "info")
    return redirect(url_for("login"))

@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        cur = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        cfm = request.form.get("confirm_password", "")
        if not check_password_hash(current_user.password_hash, cur):
            flash("Mật khẩu hiện tại không đúng", "danger")
            return render_template("change_password.html")
        if len(new) < 6:
            flash("Mật khẩu mới phải ≥ 6 ký tự", "warning")
            return render_template("change_password.html")
        if new != cfm:
            flash("Xác nhận mật khẩu không khớp", "warning")
            return render_template("change_password.html")
        current_user.password_hash = generate_password_hash(new)
        db.session.commit()
        flash("Đã đổi mật khẩu thành công", "success")
        return redirect(url_for("products"))
    return render_template("change_password.html")

# ---- Sản phẩm ----
@app.route("/products")
@login_required
def products():
    q = (request.args.get("q", "") or "").strip()
    selected_kho_req = request.args.get("kho", "ALL")

    selected_kho = enforce_staff_kho(selected_kho_req, allow_all=True)
    khos = limit_khos_for_user()
    if is_staff():
        selected_kho = current_user.assigned_kho

    like = f"%{q}%"

    if selected_kho == "ALL":
        query = db.session.query(SanPham)
        if q:
            query = query.filter(
                (SanPham.id_san_pham.like(like)) | (SanPham.ten_san_pham.like(like))
            )
        items = query.order_by(SanPham.id_san_pham).all()

        ton_rows = (
            db.session.query(TonKho.id_san_pham, func.coalesce(func.sum(TonKho.so_luong), 0))
            .group_by(TonKho.id_san_pham)
            .all()
        )
        ton_map = {k: int(v or 0) for k, v in ton_rows}
    else:
        query = (
            db.session.query(SanPham)
            .join(
                TonKho,
                (TonKho.id_san_pham == SanPham.id_san_pham) & (TonKho.id_kho == selected_kho),
            )
            .filter(TonKho.so_luong > 0)
        )
        if q:
            query = query.filter(
                (SanPham.id_san_pham.like(like)) | (SanPham.ten_san_pham.like(like))
            )

        items = (
            query.group_by(SanPham.id_san_pham)
                 .order_by(SanPham.id_san_pham)
                 .all()
        )

        ton_rows = TonKho.query.with_entities(TonKho.id_san_pham, TonKho.so_luong)\
                               .filter(TonKho.id_kho == selected_kho).all()
        ton_map = {k: int(v or 0) for k, v in ton_rows}

    return render_template(
        "products.html",
        items=items,
        q=q,
        khos=khos,
        selected_kho=selected_kho,
        ton_map=ton_map,
    )

@app.route("/products/create", methods=["GET", "POST"])
@login_required
def create_product():
    last = db.session.query(SanPham).order_by(SanPham.id_san_pham.desc()).first()
    print
    next_id = f"SP{(int(last.id_san_pham[2:]) + 1):03d}" if (last and last.id_san_pham[:2] == "SP" and last.id_san_pham[2:].isdigit()) else "SP001"

    def norm(v):
        if v is None: return None
        v = v.strip()
        return None if v == "" or v.lower() == "none" else v

    if request.method == "POST":
        sp = SanPham(
            id_san_pham=(request.form["id_san_pham"].strip() or next_id),
            ten_san_pham=request.form["ten_san_pham"].strip(),
            chat_lieu=norm(request.form.get("chat_lieu")),
            mau=norm(request.form.get("mau")),
        )
        db.session.add(sp)
        db.session.commit()
        flash(f"Đã thêm sản phẩm {sp.id_san_pham}", "success")
        return redirect(url_for("products"))
    return render_template("product_form.html", item=None, next_id=next_id)

@app.route("/products/<id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(id):
    item = db.session.get(SanPham, id)
    if not item:
        flash("Không tìm thấy sản phẩm", "warning")
        return redirect(url_for("products"))

    def norm(v):
        if v is None: return None
        v = v.strip()
        return None if v == "" or v.lower() == "none" else v

    if request.method == "POST":
        item.ten_san_pham = request.form["ten_san_pham"].strip()
        item.chat_lieu = norm(request.form.get("chat_lieu"))
        item.mau = norm(request.form.get("mau"))
        db.session.commit()
        flash("Đã cập nhật", "success")
        return redirect(url_for("products"))
    return render_template("product_form.html", item=item, next_id=item.id_san_pham)

@app.route("/products/<id>/delete", methods=["POST"])
@login_required
def delete_product(id):
    if is_staff():
        flash("Bạn không có quyền xoá sản phẩm.", "warning")
        return redirect(url_for("products"))

    sp = SanPham.query.get(id)
    if sp:
        try:
            db.session.delete(sp)
            db.session.commit()
            flash("Đã xóa sản phẩm thành công.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Không thể xóa sản phẩm vì đã có dữ liệu liên quan.", "danger")
    return redirect(url_for("products"))

# ---- Stock ----
@app.route("/stock")
@login_required
def stock():
    selected_kho_req = request.args.get("kho", "ALL")
    selected_kho = enforce_staff_kho(selected_kho_req, allow_all=True)
    khos = limit_khos_for_user()

    if is_staff():
        selected_kho = current_user.assigned_kho

    if selected_kho == "ALL":
        ton = get_ton_kho_dict(None)
        records = [(sp, ton.get(sp.id_san_pham, 0), None) for sp in SanPham.query.order_by(SanPham.id_san_pham).all()]
    else:
        ton_map = {r.id_san_pham: r.so_luong for r in TonKho.query.filter_by(id_kho=selected_kho).all()}
        records = [(sp, ton_map.get(sp.id_san_pham, 0), selected_kho) for sp in SanPham.query.order_by(SanPham.id_san_pham).all()]

    return render_template("stock.html", records=records, khos=khos, selected_kho=selected_kho)

# ---- Cảnh báo tồn thấp ----
@app.route("/canh-bao")
@login_required
def canh_bao():
    selected_kho_req = request.args.get("kho", "ALL")
    selected_kho = enforce_staff_kho(selected_kho_req, allow_all=True)
    khos = limit_khos_for_user()

    if is_staff():
        selected_kho = current_user.assigned_kho

    q = db.session.query(TonKho, SanPham).join(SanPham, TonKho.id_san_pham == SanPham.id_san_pham)
    if selected_kho != "ALL":
        q = q.filter(TonKho.id_kho == selected_kho)

    rows = q.filter(TonKho.so_luong <= TonKho.nguong_canh_bao) \
            .order_by(TonKho.id_kho, TonKho.id_san_pham).all()

    return render_template("canh_bao.html", rows=rows, khos=khos, selected_kho=selected_kho)

@app.route("/nhap-kho", methods=["GET", "POST"])
@login_required
def nhap_kho():
    last_hd = (
        db.session.query(HoaDonNhap.id_hoa_don_nhap)
        .order_by(HoaDonNhap.id_hoa_don_nhap.desc())
        .first()
    )
    next_number = _next_code_from_last(last_hd[0] if last_hd else None, "N")

    # ===== POST: lưu phiếu nhập =====
    if request.method == "POST":
        d = request.form
        try:
            id_kho = d["id_kho"].strip()
            if is_staff():
                if not current_user.assigned_kho:
                    raise ValueError("Tài khoản chưa được gán kho làm việc.")
                if id_kho != current_user.assigned_kho:
                    raise ValueError(f"Bạn chỉ được nhập kho {current_user.assigned_kho}.")

            id_sp = d["id_sp"].strip()
            so = int(d["so_luong"])

            # Gán NV: staff tự map theo username; admin chọn tự do
            id_nhan_vien = (
                USERNAME_TO_NV.get(current_user.username.lower())
                if is_staff()
                else (d.get("id_nv") or None)
            )

            rec = HoaDonNhap(
                id_hoa_don_nhap=d["id_hd"].strip(),
                id_san_pham=id_sp,
                id_kho=id_kho,
                so_san_pham_nhap=so,
                gia_nhap=float(d["gia_nhap"]),
                ngay_nhap=datetime.strptime(d["ngay"], "%Y-%m-%dT%H:%M"),
                id_nhan_vien=id_nhan_vien,
                id_nha_cung_cap=d.get("id_ncc") or None,
            )
            db.session.add(rec)

            _upsert_ton_kho(id_kho, id_sp, +so)
            db.session.commit()
            flash("Đã ghi nhận nhập kho", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Lỗi khi lưu: {e}", "danger")
        return redirect(url_for("nhap_kho"))

    # ===== GET: form & lịch sử =====
    khos = limit_khos_for_user()

    # Kho dùng cho FORM chọn sản phẩm
    if is_staff():
        selected_kho = current_user.assigned_kho
    else:
        selected_kho_req = request.args.get("kho", "ALL")
        selected_kho = enforce_staff_kho(selected_kho_req, allow_all=True)

    # ---- Bộ lọc lịch sử ----
    # Staff: chỉ lọc theo NCC; Admin: có thể lọc thêm theo NV và Kho
    f_ncc = (request.args.get("f_ncc") or "").strip()
    f_nv  = (request.args.get("f_nv")  or "").strip()  # dùng cho admin
    f_kho = (request.args.get("f_kho") or "ALL").strip()  # dùng cho admin

    q_hist = HoaDonNhap.query

    if is_staff():
        # Staff thấy TẤT CẢ phiếu trong kho được gán (kể cả NV000)
        q_hist = q_hist.filter(HoaDonNhap.id_kho == current_user.assigned_kho)
    else:
        # Admin optional filter
        if f_nv:
            q_hist = q_hist.filter(HoaDonNhap.id_nhan_vien == f_nv)
        if f_kho and f_kho != "ALL":
            q_hist = q_hist.filter(HoaDonNhap.id_kho == f_kho)

    if f_ncc:
        q_hist = q_hist.filter(HoaDonNhap.id_nha_cung_cap == f_ncc)

    items = q_hist.order_by(HoaDonNhap.ngay_nhap.desc()).limit(50).all()

    # Dropdown NV cho FORM (chỉ admin cần)
    if is_staff():
        nvs = []
        staff_nv_id = USERNAME_TO_NV.get(current_user.username.lower())
        staff_nv_label = f"{staff_nv_id} - {(current_user.full_name or current_user.username)}"
    else:
        nvs = NhanVien.query.all()
        staff_nv_id = None
        staff_nv_label = None

    nccs = NhaCungCap.query.all()

    # Sản phẩm theo kho (phục vụ FORM)
    if selected_kho == "ALL":
        sps = SanPham.query.order_by(SanPham.id_san_pham).all()
    else:
        sps = (
            db.session.query(SanPham)
            .join(
                TonKho,
                (TonKho.id_san_pham == SanPham.id_san_pham)
                & (TonKho.id_kho == selected_kho),
            )
            .filter(TonKho.so_luong > 0)
            .group_by(SanPham.id_san_pham)
            .order_by(SanPham.id_san_pham)
            .all()
        )

    return render_template(
        "nhap_kho.html",
        items=items,
        next_id_hd=next_number,
        nvs=nvs,
        nccs=nccs,
        sps=sps,
        khos=khos,
        selected_kho=selected_kho,
        staff_nv_label=staff_nv_label,
        staff_nv_id=staff_nv_id,
        # giữ các giá trị lọc để set selected ở template
        f_ncc=f_ncc,
        f_nv=f_nv,
        f_kho=f_kho,
    )


from sqlalchemy import func, cast, or_
# ...

# ---- Xuất kho ----
@app.route("/xuat-kho", methods=["GET", "POST"])
@login_required
def xuat_kho():
    last_hd = db.session.query(HoaDonXuat.id_hoa_don_xuat)\
                        .order_by(HoaDonXuat.id_hoa_don_xuat.desc()).first()
    next_number = _next_code_from_last(last_hd[0] if last_hd else None, "X")

    # ===== POST: Lưu phiếu xuất =====
    if request.method == "POST":
        d = request.form
        try:
            id_kho = d["id_kho"].strip()
            if is_staff():
                if not current_user.assigned_kho:
                    raise ValueError("Tài khoản chưa được gán kho làm việc.")
                if id_kho != current_user.assigned_kho:
                    raise ValueError(f"Bạn chỉ được xuất kho {current_user.assigned_kho}.")

            id_sp = d["id_sp"].strip()
            so_xuat = int(d["so_luong"])

            tk = db.session.get(TonKho, {"id_kho": id_kho, "id_san_pham": id_sp})
            ton = (tk.so_luong if tk else 0)
            if so_xuat > ton:
                flash(f"Số lượng tại kho {id_kho} không đủ! Hiện chỉ còn {ton}.", "danger")
                return redirect(url_for("xuat_kho"))

            # staff: tự gán mã NV
            if is_staff():
                id_nhan_vien = USERNAME_TO_NV.get(current_user.username.lower())
            else:
                id_nhan_vien = (d.get("id_nv") or None)

            rec = HoaDonXuat(
                id_hoa_don_xuat=d["id_hd"].strip(),
                id_san_pham=id_sp,
                id_kho=id_kho,
                so_san_pham_xuat=so_xuat,
                gia_ban=float(d.get("gia_ban", 0)),
                ngay_xuat=datetime.strptime(d["ngay"], "%Y-%m-%dT%H:%M"),
                id_nhan_vien=id_nhan_vien,
                id_xe_van_chuyen=d.get("id_xe") or None,
                id_khach_hang=d.get("id_kh") or None,
            )
            db.session.add(rec)
            _upsert_ton_kho(id_kho, id_sp, -so_xuat)
            db.session.commit()
            flash("✅ Đã ghi nhận phiếu xuất kho", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Lỗi khi lưu: {e}", "danger")
        return redirect(url_for("xuat_kho"))

    # ===== GET =====
    khos = limit_khos_for_user()

    # Kho cho FORM
    selected_kho_req = request.args.get("kho", "ALL")
    selected_kho = enforce_staff_kho(selected_kho_req, allow_all=True)
    if is_staff():
        selected_kho = current_user.assigned_kho

    # Lấy filter
    f_xe = (request.args.get("f_xe") or "").strip()
    f_kh = (request.args.get("f_kh") or "").strip()
    if is_staff():
        f_nv  = USERNAME_TO_NV.get(current_user.username.lower()) or ""
        f_kho = current_user.assigned_kho
    else:
        f_nv  = (request.args.get("f_nv")  or "").strip()
        f_kho = (request.args.get("f_kho") or "ALL").strip()

    # Lịch sử
    q_hist = HoaDonXuat.query
    if is_staff():
        # staff: luôn bó theo kho của mình
        q_hist = q_hist.filter(HoaDonXuat.id_kho == current_user.assigned_kho)
        # hiển thị cả phiếu có id_nhan_vien = NV của mình HOẶC NULL (các phiếu cũ)
        nv_self = USERNAME_TO_NV.get(current_user.username.lower())
        if nv_self:
            q_hist = q_hist.filter(or_(HoaDonXuat.id_nhan_vien == nv_self,
                                       HoaDonXuat.id_nhan_vien.is_(None)))
    else:
        if f_nv:
            q_hist = q_hist.filter(HoaDonXuat.id_nhan_vien == f_nv)
        if f_kho and f_kho != "ALL":
            q_hist = q_hist.filter(HoaDonXuat.id_kho == f_kho)

    if f_xe:
        q_hist = q_hist.filter(HoaDonXuat.id_xe_van_chuyen == f_xe)
    if f_kh:
        q_hist = q_hist.filter(HoaDonXuat.id_khach_hang == f_kh)

    items = q_hist.order_by(HoaDonXuat.ngay_xuat.desc()).limit(50).all()

    # Dropdown cho form
    if is_staff():
        nvs = []
        staff_nv_label = current_user.full_name or current_user.username
    else:
        nvs = NhanVien.query.all()
        staff_nv_label = None

    # Sản phẩm theo kho FORM
    if selected_kho == "ALL":
        sps = SanPham.query.order_by(SanPham.id_san_pham).all()
    else:
        sps = (
            db.session.query(SanPham)
            .join(TonKho, (TonKho.id_san_pham == SanPham.id_san_pham) & (TonKho.id_kho == selected_kho))
            .filter(TonKho.so_luong > 0)
            .group_by(SanPham.id_san_pham)
            .order_by(SanPham.id_san_pham)
            .all()
        )

    xes = XeVanChuyen.query.all()
    khs = KhachHang.query.all()

    return render_template(
        "xuat_kho.html",
        items=items,
        next_id_hd=next_number,
        sps=sps,
        nvs=nvs,
        xes=xes,
        khs=khs,
        khos=khos,
        selected_kho=selected_kho,
        staff_nv_label=staff_nv_label,
        f_nv=f_nv, f_xe=f_xe, f_kh=f_kh, f_kho=f_kho
    )

# ---- Điều chuyển (ADMIN ONLY) ----
@app.route("/dieu-chuyen", methods=["GET", "POST"])
@login_required
def dieu_chuyen():
    if is_staff():
        flash("Bạn không có quyền điều chuyển hàng.", "warning")
        return redirect(url_for("home_page"))

    last_dc = db.session.query(DieuChuyen.id_dieu_chuyen)\
                        .order_by(DieuChuyen.id_dieu_chuyen.desc()).first()
    next_id = _next_code_from_last(last_dc[0] if last_dc else None, "DC")

    khos = Kho.query.order_by(Kho.id_kho).all()
    sps  = SanPham.query.order_by(SanPham.id_san_pham).all()

    if request.method == "POST":
        d = request.form
        kho_src = (d.get("kho_src") or "").strip()
        kho_dst = (d.get("kho_dst") or "").strip()

        if not kho_src or not kho_dst:
            flash("Vui lòng chọn kho nguồn và kho đích.", "warning")
            return redirect(url_for("dieu_chuyen"))
        if kho_src == kho_dst:
            flash("Kho nguồn và kho đích phải khác nhau.", "warning")
            return redirect(url_for("dieu_chuyen"))

        try:
            ngay = datetime.strptime(d.get("ngay"), "%Y-%m-%dT%H:%M")
        except Exception:
            flash("Ngày không hợp lệ.", "warning")
            return redirect(url_for("dieu_chuyen"))

        note = (d.get("ghi_chu") or "").strip() or None

        sp_ids  = d.getlist("id_sp[]")
        sl_list = d.getlist("so_luong[]")
        lines = []
        for sp, sl in zip(sp_ids, sl_list):
            sp = (sp or "").strip()
            try:
                qty = int(sl)
            except Exception:
                qty = 0
            if sp and qty > 0:
                lines.append((sp, qty))

        if not lines:
            flash("Chưa chọn sản phẩm / số lượng hợp lệ.", "warning")
            return redirect(url_for("dieu_chuyen"))

        try:
            for sp, qty in lines:
                tk = db.session.get(TonKho, {"id_kho": kho_src, "id_san_pham": sp})
                ton = tk.so_luong if tk else 0
                if qty > ton:
                    raise ValueError(f"Kho {kho_src} không đủ hàng cho {sp}. Còn {ton}, yêu cầu {qty}.")

            for sp, qty in lines:
                _upsert_ton_kho(kho_src, sp, -qty)
                _upsert_ton_kho(kho_dst, sp, +qty)

            hdr = DieuChuyen(
                id_dieu_chuyen=(d.get("id_dc") or next_id).strip(),
                kho_nguon=kho_src,
                kho_dich=kho_dst,
                ngay_dc=ngay,
                ghi_chu=note
            )
            db.session.add(hdr)
            for sp, qty in lines:
                db.session.add(DieuChuyenCT(
                    id_dieu_chuyen=hdr.id_dieu_chuyen,
                    id_san_pham=sp,
                    so_luong=qty
                ))

            db.session.commit()
            flash("✅ Đã ghi nhận điều chuyển.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Lỗi điều chuyển: {e}", "danger")

        return redirect(url_for("dieu_chuyen"))

    recent = db.session.query(DieuChuyen, DieuChuyenCT)\
        .join(DieuChuyenCT, DieuChuyen.id_dieu_chuyen == DieuChuyenCT.id_dieu_chuyen)\
        .order_by(DieuChuyen.ngay_dc.desc()).limit(10).all()

    return render_template("dieu_chuyen.html",
                           khos=khos, sps=sps, next_id_dc=next_id, recent=recent)

# ==== THỐNG KÊ DOANH THU & BÁN CHẠY ====
@app.route("/doanh-thu")
@login_required
def doanh_thu_view():
    kho_req = request.args.get("kho", "ALL")
    selected_kho = enforce_staff_kho(kho_req, allow_all=True)
    if is_staff():
        selected_kho = current_user.assigned_kho

    def _d(s, end=False):
        if not s:
            d = datetime.now() - (timedelta(days=29) if not end else timedelta(0))
            if end:
                d = datetime.now()
            return d.replace(hour=(23 if end else 0), minute=(59 if end else 0), second=59)
        try:
            if "T" in s:
                dt = datetime.strptime(s, "%Y-%m-%dT%H:%M")
            else:
                dt = datetime.strptime(s, "%Y-%m-%d")
            if "T" not in s:
                dt = dt.replace(hour=(23 if end else 0), minute=(59 if end else 0), second=59)
            return dt
        except:
            return None

    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    fdt = _d(date_from, end=False)
    tdt = _d(date_to, end=True)

    # --- Doanh thu theo ngày ---
    q_rev = db.session.query(
        cast(HoaDonXuat.ngay_xuat, Date).label("d"),
        func.coalesce(func.sum(HoaDonXuat.so_san_pham_xuat * HoaDonXuat.gia_ban), 0).label("revenue")
    )
    if selected_kho != "ALL":
        q_rev = q_rev.filter(HoaDonXuat.id_kho == selected_kho)
    if fdt:
        q_rev = q_rev.filter(HoaDonXuat.ngay_xuat >= fdt)
    if tdt:
        q_rev = q_rev.filter(HoaDonXuat.ngay_xuat <= tdt)
    q_rev = q_rev.group_by(cast(HoaDonXuat.ngay_xuat, Date)).order_by(cast(HoaDonXuat.ngay_xuat, Date))
    daily_rev = q_rev.all()

    # --- Giá vốn: theo giá nhập gần nhất ---
    from sqlalchemy.orm import aliased
    hn = aliased(HoaDonNhap)

    sub_latest_import = db.session.query(
        hn.id_kho.label("kho"),
        hn.id_san_pham.label("sp"),
        func.max(hn.ngay_nhap).label("latest")
    ).group_by(hn.id_kho, hn.id_san_pham).subquery()

    sub_cogs_price = db.session.query(
        hn.id_kho, hn.id_san_pham, hn.gia_nhap
    ).join(
        sub_latest_import,
        (hn.id_kho == sub_latest_import.c.kho)
        & (hn.id_san_pham == sub_latest_import.c.sp)
        & (hn.ngay_nhap == sub_latest_import.c.latest)
    ).subquery()

    q_cogs = db.session.query(
        cast(HoaDonXuat.ngay_xuat, Date).label("d"),
        func.coalesce(func.sum(HoaDonXuat.so_san_pham_xuat * sub_cogs_price.c.gia_nhap), 0).label("cogs")
    ).join(
        sub_cogs_price,
        (HoaDonXuat.id_kho == sub_cogs_price.c.id_kho)
        & (HoaDonXuat.id_san_pham == sub_cogs_price.c.id_san_pham)
    )
    if selected_kho != "ALL":
        q_cogs = q_cogs.filter(HoaDonXuat.id_kho == selected_kho)
    if fdt:
        q_cogs = q_cogs.filter(HoaDonXuat.ngay_xuat >= fdt)
    if tdt:
        q_cogs = q_cogs.filter(HoaDonXuat.ngay_xuat <= tdt)
    q_cogs = q_cogs.group_by(cast(HoaDonXuat.ngay_xuat, Date))
    daily_cogs = dict(q_cogs.all())

    # --- Lợi nhuận ---
    rows = []
    total_rev = total_cogs = 0.0
    for d, rev in daily_rev:
        cogs = float(daily_cogs.get(d, 0.0))
        prof = float(rev) - cogs
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "revenue": float(rev),
            "cogs": cogs,
            "profit": prof
        })
        total_rev += float(rev)
        total_cogs += cogs
    total_profit = total_rev - total_cogs

    # --- Top bán chạy ---
    q_top_qty = db.session.query(
        HoaDonXuat.id_san_pham,
        func.coalesce(func.sum(HoaDonXuat.so_san_pham_xuat), 0).label("qty")
    )
    if selected_kho != "ALL":
        q_top_qty = q_top_qty.filter(HoaDonXuat.id_kho == selected_kho)
    if fdt:
        q_top_qty = q_top_qty.filter(HoaDonXuat.ngay_xuat >= fdt)
    if tdt:
        q_top_qty = q_top_qty.filter(HoaDonXuat.ngay_xuat <= tdt)
    top_by_qty = q_top_qty.group_by(HoaDonXuat.id_san_pham)\
        .order_by(func.sum(HoaDonXuat.so_san_pham_xuat).desc())\
        .limit(10).all()

    q_top_rev = db.session.query(
        HoaDonXuat.id_san_pham,
        func.coalesce(func.sum(HoaDonXuat.so_san_pham_xuat * HoaDonXuat.gia_ban), 0).label("amt")
    )
    if selected_kho != "ALL":
        q_top_rev = q_top_rev.filter(HoaDonXuat.id_kho == selected_kho)
    if fdt:
        q_top_rev = q_top_rev.filter(HoaDonXuat.ngay_xuat >= fdt)
    if tdt:
        q_top_rev = q_top_rev.filter(HoaDonXuat.ngay_xuat <= tdt)
    top_by_rev = q_top_rev.group_by(HoaDonXuat.id_san_pham)\
        .order_by(func.sum(HoaDonXuat.so_san_pham_xuat * HoaDonXuat.gia_ban).desc())\
        .limit(10).all()

    return render_template(
        "doanh_thu.html",
        khos=limit_khos_for_user(),
        selected_kho=selected_kho,
        date_from=date_from,
        date_to=date_to,
        rows=rows,
        total_rev=total_rev,
        total_cogs=total_cogs,
        total_profit=total_profit,
        top_by_qty=top_by_qty,
        top_by_rev=top_by_rev
    )

# ---- Danh mục view-only ----
@app.route("/dm/kho")
@login_required
def kho_list():
    rows = db.session.query(Kho).order_by(Kho.id_kho).all()
    data = [(r.id_kho, r.ten_kho, r.id_dia_diem) for r in rows]
    headers = ["Mã kho", "Tên kho", "Địa điểm"]
    return render_template("list_generic.html", title="Kho hàng", headers=headers, rows=data)

@app.route("/dm/dia-diem")
@login_required
def dia_diem_list():
    rows = db.session.query(DiaDiem).order_by(DiaDiem.id_dia_diem).all()
    data = [(r.id_dia_diem, r.ten_dia_diem) for r in rows]
    return render_template("list_generic.html", title="Địa điểm", headers=["Mã", "Tên"], rows=data)

# ==== QUẢN LÝ NHÀ CUNG CẤP (ADMIN CRUD) ====
@app.route("/dm/nha-cung-cap/manage")
@login_required
def ncc_manage():
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("home_page"))

    q = request.args.get("q", "").strip()
    qry = NhaCungCap.query
    if q:
        q_like = f"%{q}%"
        qry = qry.filter(
            (NhaCungCap.id_nha_cung_cap.ilike(q_like)) |
            (NhaCungCap.ten_nha_cung_cap.ilike(q_like)) |
            (NhaCungCap.so_dien_thoai_nha_cung_cap.ilike(q_like))
        )
    rows = qry.order_by(NhaCungCap.id_nha_cung_cap).all()
    return render_template("ncc_manage.html", rows=rows, q=q)

@app.route("/dm/nha-cung-cap/create", methods=["GET","POST"])
@login_required
def ncc_create():
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("ncc_manage"))

    if request.method == "POST":
        d = request.form
        ncc = NhaCungCap(
            id_nha_cung_cap=d.get("id_nha_cung_cap").strip(),
            ten_nha_cung_cap=d.get("ten_nha_cung_cap").strip(),
            so_dien_thoai_nha_cung_cap=(d.get("so_dien_thoai_nha_cung_cap") or "").strip() or None,
            id_dia_chi=(d.get("dia_diem") or "").strip() or None,
        )
        db.session.add(ncc)
        db.session.commit()
        flash("Đã thêm nhà cung cấp.", "success")
        return redirect(url_for("ncc_manage"))

    last = NhaCungCap.query.order_by(NhaCungCap.id_nha_cung_cap.desc()).first()
    next_id = "NCC001"
    if last:
        try:
            so = int(last.id_nha_cung_cap[3:]) + 1
        except:
            so = 1
        next_id = f"NCC{so:03d}"

    dds = DiaDiem.query.all()
    return render_template("ncc_form.html", item=None, dds=dds, next_id=next_id)

@app.route("/dm/nha-cung-cap/<id>/edit", methods=["GET","POST"])
@login_required
def ncc_edit(id):
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("ncc_manage"))

    item = db.session.get(NhaCungCap, id)
    if not item:
        flash("Không tìm thấy nhà cung cấp.", "warning")
        return redirect(url_for("ncc_manage"))

    if request.method == "POST":
        d = request.form
        item.ten_nha_cung_cap = d.get("ten_nha_cung_cap").strip()
        item.so_dien_thoai_nha_cung_cap = (d.get("so_dien_thoai_nha_cung_cap") or "").strip() or None
        item.id_dia_chi = (d.get("dia_diem") or "").strip() or None
        db.session.commit()
        flash("Đã cập nhật.", "success")
        return redirect(url_for("ncc_manage"))

    dds = DiaDiem.query.all()
    return render_template("ncc_form.html", item=item, dds=dds)

@app.route("/dm/nha-cung-cap/<id>/delete", methods=["POST"])
@login_required
def ncc_delete(id):
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("ncc_manage"))

    item = db.session.get(NhaCungCap, id)
    if item:
        try:
            db.session.delete(item)
            db.session.commit()
            flash("Đã xóa.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Không thể xóa: đã có dữ liệu liên quan.", "danger")
    return redirect(url_for("ncc_manage"))

# ==== QUẢN LÝ KHÁCH HÀNG (ADMIN CRUD) ====
@app.route("/dm/khach-hang/manage")
@login_required
def kh_manage():
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("home_page"))

    q = request.args.get("q", "").strip()
    query = KhachHang.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (KhachHang.id_khach_hang.ilike(like)) |
            (KhachHang.ho.ilike(like)) |
            (KhachHang.ten_dem.ilike(like)) |
            (KhachHang.ten.ilike(like)) |
            (KhachHang.so_dien_thoai.ilike(like))
        )
    rows = query.order_by(KhachHang.id_khach_hang).all()
    return render_template("kh_manage.html", rows=rows, q=q)

@app.route("/dm/khach-hang/create", methods=["GET","POST"])
@login_required
def kh_create():
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("kh_manage"))

    last = KhachHang.query.order_by(KhachHang.id_khach_hang.desc()).first()
    next_id = "KH001"
    if last:
        try:
            so = int(last.id_khach_hang[2:]) + 1
        except:
            so = 1
        next_id = f"KH{so:03d}"

    if request.method == "POST":
        d = request.form
        kh = KhachHang(
            id_khach_hang=d.get("id_khach_hang").strip(),
            ho=(d.get("ho") or "").strip() or None,
            ten_dem=(d.get("ten_dem") or "").strip() or None,
            ten=(d.get("ten") or "").strip() or None,
            so_dien_thoai=(d.get("so_dien_thoai") or "").strip() or None,
            id_dia_chi=(d.get("dia_diem") or "").strip() or None,
        )
        db.session.add(kh)
        db.session.commit()
        flash("Đã thêm khách hàng.", "success")
        return redirect(url_for("kh_manage"))

    dds = DiaDiem.query.all()
    return render_template("kh_form.html", item=None, dds=dds, next_id=next_id)

@app.route("/dm/khach-hang/<id>/edit", methods=["GET","POST"])
@login_required
def kh_edit(id):
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("kh_manage"))

    item = db.session.get(KhachHang, id)
    if not item:
        flash("Không tìm thấy khách hàng.", "warning")
        return redirect(url_for("kh_manage"))

    if request.method == "POST":
        d = request.form
        item.ho = (d.get("ho") or "").strip() or None
        item.ten_dem = (d.get("ten_dem") or "").strip() or None
        item.ten = (d.get("ten") or "").strip() or None
        item.so_dien_thoai = (d.get("so_dien_thoai") or "").strip() or None
        item.id_dia_chi = (d.get("dia_diem") or "").strip() or None
        db.session.commit()
        flash("Đã cập nhật.", "success")
        return redirect(url_for("kh_manage"))

    dds = DiaDiem.query.all()
    return render_template("kh_form.html", item=item, dds=dds)

@app.route("/dm/khach-hang/<id>/delete", methods=["POST"])
@login_required
def kh_delete(id):
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("kh_manage"))

    item = db.session.get(KhachHang, id)
    if item:
        try:
            db.session.delete(item)
            db.session.commit()
            flash("Đã xóa.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Không thể xóa: đã có dữ liệu liên quan.", "danger")
    return redirect(url_for("kh_manage"))

# ==== QUẢN LÝ XE VẬN CHUYỂN (ADMIN CRUD) ====
@app.route("/dm/xe/manage")
@login_required
def xe_manage():
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("home_page"))

    q = request.args.get("q", "").strip()
    query = XeVanChuyen.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (XeVanChuyen.id_xe_van_chuyen.ilike(like)) |
            (XeVanChuyen.bien_so.ilike(like))
        )
    rows = query.order_by(XeVanChuyen.id_xe_van_chuyen).all()
    return render_template("xe_manage.html", rows=rows, q=q)

def next_xe_id():
    last = db.session.query(XeVanChuyen.id_xe_van_chuyen).order_by(
        XeVanChuyen.id_xe_van_chuyen.desc()
    ).first()
    if not last:
        return "VC001"
    num = int(last[0][2:]) + 1
    return f"VC{num:03d}"

@app.route("/dm/xe/create", methods=["GET", "POST"])
@login_required
def xe_create():
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("xe_manage"))

    next_id = next_xe_id()

    if request.method == "POST":
        d = request.form
        xe = XeVanChuyen(
            id_xe_van_chuyen=d["id_xe_van_chuyen"].strip(),
            bien_so=d["bien_so"].strip(),
            ho=(d.get("ho") or "").strip() or None,
            ten_dem=(d.get("ten_dem") or "").strip() or None,
            ten=(d.get("ten") or "").strip() or None,
            so_dien_thoai_tai_xe=(d.get("so_dien_thoai_tai_xe") or "").strip() or None,
        )
        db.session.add(xe)
        db.session.commit()
        flash("Đã thêm xe vận chuyển.", "success")
        return redirect(url_for("xe_manage"))

    return render_template("xe_form.html", item=None, next_id=next_id)

@app.route("/dm/xe/<id>/edit", methods=["GET", "POST"])
@login_required
def xe_edit(id):
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("xe_manage"))

    item = db.session.get(XeVanChuyen, id)
    if not item:
        flash("Không tìm thấy xe.", "warning")
        return redirect(url_for("xe_manage"))

    if request.method == "POST":
        d = request.form
        item.bien_so = d["bien_so"].strip()
        item.ho = (d.get("ho") or "").strip() or None
        item.ten_dem = (d.get("ten_dem") or "").strip() or None
        item.ten = (d.get("ten") or "").strip() or None
        item.so_dien_thoai_tai_xe = (d.get("so_dien_thoai_tai_xe") or "").strip() or None
        db.session.commit()
        flash("Đã cập nhật.", "success")
        return redirect(url_for("xe_manage"))

    return render_template("xe_form.html", item=item)

@app.route("/dm/xe/<id>/delete", methods=["POST"])
@login_required
def xe_delete(id):
    if not is_admin():
        flash("Bạn không có quyền.", "warning")
        return redirect(url_for("xe_manage"))

    item = db.session.get(XeVanChuyen, id)
    if item:
        try:
            db.session.delete(item)
            db.session.commit()
            flash("Đã xóa.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Không thể xóa: đã có dữ liệu liên quan.", "danger")
    return redirect(url_for("xe_manage"))

# ---- Home (dashboard) ----
@app.route("/home")
@login_required
def home_page():
    selected_kho_req = request.args.get("kho", "ALL")
    selected_kho = enforce_staff_kho(selected_kho_req, allow_all=True)
    khos = limit_khos_for_user()

    if is_staff():
        selected_kho = current_user.assigned_kho

    if selected_kho == "ALL":
        stat_sp = (
            db.session.query(func.count(func.distinct(SanPham.id_san_pham)))
            .scalar() or 0
        )
    else:
        stat_sp = (
            db.session.query(func.count(func.distinct(TonKho.id_san_pham)))
            .filter(TonKho.id_kho == selected_kho, TonKho.so_luong > 0)
            .scalar() or 0
        )

    if selected_kho == "ALL":
        nhap_sum = db.session.query(func.coalesce(func.sum(TonKho.so_luong), 0)).scalar() or 0
        stat_don = db.session.query(func.count(func.distinct(HoaDonXuat.id_hoa_don_xuat))).scalar() or 0
    else:
        nhap_sum = db.session.query(func.coalesce(func.sum(TonKho.so_luong), 0))\
                             .filter(TonKho.id_kho == selected_kho).scalar() or 0
        stat_don = db.session.query(func.count(func.distinct(HoaDonXuat.id_hoa_don_xuat)))\
                             .filter(HoaDonXuat.id_kho == selected_kho).scalar() or 0
    stat_ton = int(nhap_sum)

    latest_nhap = db.session.query(func.max(HoaDonNhap.ngay_nhap))
    latest_xuat = db.session.query(func.max(HoaDonXuat.ngay_xuat))
    if selected_kho != "ALL":
        latest_nhap = latest_nhap.filter(HoaDonNhap.id_kho == selected_kho)
        latest_xuat = latest_xuat.filter(HoaDonXuat.id_kho == selected_kho)
    latest_nhap = latest_nhap.scalar()
    latest_xuat = latest_xuat.scalar()

    from datetime import datetime as _dt
    def _to_dt(v):
        if hasattr(v, "strftime"): return v
        if v is None: return None
        try:
            s = str(v).strip()
            if " " in s and "T" not in s: s = s.replace(" ", "T")
            return _dt.fromisoformat(s)
        except Exception:
            return None

    candidates = list(filter(None, (_to_dt(latest_nhap), _to_dt(latest_xuat))))
    stat_latest = candidates and max(candidates).strftime("%d/%m/%Y %H:%M") or "—"

    return render_template(
        "home.html",
        stat_sp=stat_sp,
        stat_ton=stat_ton,
        stat_don=stat_don,
        stat_latest=stat_latest,
        khos=khos,
        selected_kho=selected_kho,
    )

# -----------------------------------------------------------------------------
# CLI util
# -----------------------------------------------------------------------------
import click

@app.cli.command("set-password")
@click.argument("username")
@click.argument("password")
def set_password(username, password):
    u = User.query.filter_by(username=username).first()
    if not u:
        print("User không tồn tại:", username)
        return
    u.password_hash = generate_password_hash(password)
    db.session.commit()
    print("Đã đổi mật khẩu cho", username)

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
