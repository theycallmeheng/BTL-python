import os

class Config:
    # ===== Cấu hình cơ bản =====
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-please")

    # Kết nối MySQL (sửa lại user/pass nếu cần)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:admin123@localhost/quan_ly_kho?charset=utf8mb4",
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ===== Bootstrap tài khoản mặc định =====
    BOOTSTRAP_ADMIN = True  # bật tính năng tự tạo user mặc định nếu trống

    # --- Admin mặc định ---
    DEFAULT_ADMIN_USER = "admin"
    DEFAULT_ADMIN_PASS = "admin123"
    DEFAULT_ADMIN_NAME = "Quản trị hệ thống"

    # --- Danh sách nhân viên mặc định ---
    DEFAULT_STAFF_ACCOUNTS = [
        {
            "username": "nv1",
            "password": "123456",
            "full_name": "Nhân viên Kho 1",
            "assigned_kho": "K1",
        },
        {
            "username": "nv2",
            "password": "123456",
            "full_name": "Nhân viên Kho 2",
            "assigned_kho": "K2",
        },
        {
            "username": "nv3",
            "password": "123456",
            "full_name": "Nhân viên Kho 3",
            "assigned_kho": "K3",
        },
    ]
