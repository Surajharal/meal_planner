"""Session-based authentication: email users, OTP signup, and .env admin credentials."""
import hmac
import logging
import secrets
import smtplib
import time
from datetime import datetime, timedelta

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from email_service import send_otp_email
from models import SessionLocal, SignupVerification, User
from rbac import ALL_ROLES, ROLE_ADMIN, ROLE_GYAMA
from validators import normalize_email, validate_email, validate_password

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 10
SIGNUP_VERIFY_SESSION_SECONDS = 15 * 60
MAX_OTP_SENDS_PER_HOUR = 5

_PUBLIC_ENDPOINTS = frozenset(
    {
        "login",
        "admin_login",
        "logout",
        "static",
        "health",
        "register_send_otp",
        "register_verify_otp",
        "register_complete",
    }
)


def _ct_equal(a: str, b: str) -> bool:
    if not a or not b or len(a) != len(b):
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def ensure_admin_user_row():
    """
    Ensure a User row exists for ADMIN_USERNAME with role admin.
    Admin signs in with credentials from .env only (not DB password_hash).
    """
    db = SessionLocal()
    try:
        un = (Config.ADMIN_USERNAME or "admin").strip()
        if not un:
            return
        u = db.query(User).filter(User.username == un).first()
        if u:
            if u.role != ROLE_ADMIN:
                u.role = ROLE_ADMIN
                db.commit()
            return
        placeholder = generate_password_hash("use-env-admin-password-not-db")
        db.add(
            User(
                username=un,
                email=None,
                password_hash=placeholder,
                role=ROLE_ADMIN,
            )
        )
        db.commit()
        logger.info("Created admin user row for username %s (sign in via ADMIN_PASSWORD in .env)", un)
    finally:
        db.close()


def _safe_redirect_path(next_url: str):
    if not next_url or not isinstance(next_url, str):
        return None
    s = next_url.strip()
    if "://" in s or not s.startswith("/") or s.startswith("//"):
        return None
    return s


def _request_expects_json_response():
    if request.path.startswith("/api/"):
        return True
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def _find_user_by_email(db, email: str):
    """Resolve user by email column or legacy username == email."""
    return (
        db.query(User).filter(User.email == email).first()
        or db.query(User).filter(User.username == email).first()
    )


def _login_session(user: User):
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.email or user.username
    user_role = getattr(user, "role", None) or ROLE_GYAMA
    if user_role == "alpha":
        user_role = ROLE_GYAMA
    if user_role not in ALL_ROLES:
        user_role = ROLE_GYAMA
    session["role"] = user_role


def register_auth(app):
    """Register login/logout, signup OTP routes, and global before_request guard."""
    from extensions import limiter

    @app.before_request
    def require_login():
        ep = request.endpoint
        if ep in _PUBLIC_ENDPOINTS:
            return None
        if request.blueprint == "static":
            return None
        if session.get("user_id"):
            return None
        if _request_expects_json_response():
            return jsonify({"success": False, "message": "Authentication required"}), 401
        fp = request.path
        if request.query_string:
            fp += "?" + request.query_string.decode()
        if fp.startswith("/login") and not fp.startswith("/login/admin"):
            fp = "/"
        return redirect(url_for("login", next=fp))

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("20/minute", methods=["POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("index"))

        next_raw = (request.form.get("next") if request.method == "POST" else None) or (
            request.args.get("next") or ""
        )
        raw_tab = (request.form.get("tab") if request.method == "POST" else None) or request.args.get(
            "tab", "user"
        )
        tab = raw_tab if raw_tab in ("user", "signup") else "user"

        if request.method == "POST":
            # Standard user: email + password only (admin uses /login/admin)
            ok_e, err_e, email = validate_email(request.form.get("email") or "")
            password = (request.form.get("password") or "").strip()
            if not ok_e:
                flash(err_e or "Invalid email.", "error")
                return render_template("login.html", next=next_raw, tab="user")
            ok_p, err_p = validate_password(password)
            if not ok_p:
                flash(err_p or "Invalid password.", "error")
                return render_template("login.html", next=next_raw, tab="user")

            db = SessionLocal()
            try:
                user_by_email = _find_user_by_email(db, email)
                env_email_admin = (
                    Config.ADMIN_LOGIN_EMAIL
                    and email == Config.ADMIN_LOGIN_EMAIL
                    and Config.ADMIN_PASSWORD
                    and _ct_equal(password, Config.ADMIN_PASSWORD)
                )
                # Sign in on /login with AUTH_EMAIL + env password (same as /login/admin)
                if env_email_admin:
                    if user_by_email and user_by_email.username != Config.ADMIN_USERNAME:
                        flash("Unknown email or wrong password.", "error")
                        return render_template("login.html", next=next_raw, tab="user")
                    user = db.query(User).filter(User.username == Config.ADMIN_USERNAME).first()
                    if not user:
                        flash(
                            "Admin account is not provisioned. Restart the app after DB migration.",
                            "error",
                        )
                        return render_template("login.html", next=next_raw, tab="user")
                    if user.role != ROLE_ADMIN:
                        user.role = ROLE_ADMIN
                        db.commit()
                    _login_session(user)
                    flash("Signed in successfully.", "success")
                    nxt = _safe_redirect_path(next_raw)
                    return redirect(nxt) if nxt else redirect(url_for("index"))

                if not user_by_email:
                    flash("Unknown email or wrong password.", "error")
                    return render_template("login.html", next=next_raw, tab="user")
                if user_by_email.role == ROLE_ADMIN and user_by_email.username == Config.ADMIN_USERNAME:
                    flash(
                        "Set AUTH_EMAIL or ADMIN_EMAIL in .env to this address to sign in here, "
                        "or use /login/admin with ADMIN_USERNAME.",
                        "error",
                    )
                    return render_template("login.html", next=next_raw, tab="user")
                if not check_password_hash(user_by_email.password_hash, password):
                    flash("Unknown email or wrong password.", "error")
                    return render_template("login.html", next=next_raw, tab="user")
                _login_session(user_by_email)
            finally:
                db.close()

            flash("Signed in successfully.", "success")
            nxt = _safe_redirect_path(next_raw)
            return redirect(nxt) if nxt else redirect(url_for("index"))

        return render_template("login.html", next=next_raw, tab=tab)

    @app.route("/login/admin", methods=["GET", "POST"])
    @limiter.limit("20/minute", methods=["POST"])
    def admin_login():
        """Env-based admin sign-in; not linked from the public login UI."""
        if session.get("user_id"):
            return redirect(url_for("index"))

        next_raw = (request.form.get("next") if request.method == "POST" else None) or (
            request.args.get("next") or ""
        )

        if request.method == "POST":
            admin_user = (request.form.get("admin_username") or "").strip()
            admin_pass = request.form.get("admin_password") or ""
            if not admin_user or not admin_pass:
                flash("Enter admin username and password.", "error")
                return render_template("admin_login.html", next=next_raw)
            if not Config.ADMIN_PASSWORD:
                flash(
                    "Admin password is not set in the server environment (ADMIN_PASSWORD).",
                    "error",
                )
                return render_template("admin_login.html", next=next_raw)
            if not _ct_equal(admin_user, Config.ADMIN_USERNAME) or not _ct_equal(
                admin_pass, Config.ADMIN_PASSWORD
            ):
                flash("Invalid admin credentials.", "error")
                return render_template("admin_login.html", next=next_raw)

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.username == Config.ADMIN_USERNAME).first()
                if not user:
                    flash("Admin account is not provisioned. Restart the app after DB migration.", "error")
                    return render_template("admin_login.html", next=next_raw)
                if user.role != ROLE_ADMIN:
                    user.role = ROLE_ADMIN
                    db.commit()
                _login_session(user)
            finally:
                db.close()

            flash("Signed in as administrator.", "success")
            nxt = _safe_redirect_path(next_raw)
            return redirect(nxt) if nxt else redirect(url_for("index"))

        return render_template("admin_login.html", next=next_raw)

    @app.route("/register/send-otp", methods=["POST"])
    @limiter.limit("10/hour")
    def register_send_otp():
        if session.get("user_id"):
            return redirect(url_for("index"))
        next_raw = request.form.get("next") or ""
        ok, err, email = validate_email(request.form.get("email") or "")
        if not ok:
            flash(err or "Invalid email.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))

        db = SessionLocal()
        try:
            if _find_user_by_email(db, email):
                flash("An account with this email already exists. Sign in instead.", "error")
                return redirect(url_for("login", tab="user", next=next_raw or None))

            since = datetime.utcnow() - timedelta(hours=1)
            db.query(SignupVerification).filter(
                SignupVerification.email == email,
                SignupVerification.expires_at < datetime.utcnow(),
            ).delete(synchronize_session=False)
            sent_last_hour = (
                db.query(SignupVerification)
                .filter(SignupVerification.email == email, SignupVerification.created_at >= since)
                .count()
            )
            if sent_last_hour >= MAX_OTP_SENDS_PER_HOUR:
                flash("Too many verification attempts. Try again in about an hour.", "error")
                return redirect(url_for("login", tab="signup", next=next_raw or None))

            otp = f"{secrets.randbelow(1000000):06d}"
            otp_hash = generate_password_hash(otp)
            expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        except Exception:
            logger.exception("register_send_otp DB error")
            db.rollback()
            flash("Could not start sign-up. Try again.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        finally:
            db.close()

        try:
            send_otp_email(email, otp)
        except smtplib.SMTPAuthenticationError:
            logger.exception("send_otp_email failed (SMTP rejected username/password)")
            flash(
                "Could not send email: the mail server rejected the login. "
                "For Gmail, use an App Password (Google Account → Security → App passwords) "
                "in SMTP_PASSWORD, with SMTP_USER set to your full Gmail address. "
                "Check .env in the container matches what you expect.",
                "error",
            )
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        except Exception as ex:
            logger.exception("send_otp_email failed")
            flash(str(ex) or "Could not send email.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))

        db = SessionLocal()
        try:
            db.add(
                SignupVerification(
                    email=email,
                    otp_hash=otp_hash,
                    expires_at=expires_at,
                )
            )
            db.commit()
        except Exception:
            logger.exception("register_send_otp persist OTP failed")
            db.rollback()
            flash("Could not save verification. Try again.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        finally:
            db.close()

        session["signup_pending_email"] = email
        session.pop("signup_verified_email", None)
        session.pop("signup_verified_at", None)
        if not Config.SIGNUP_OTP_EMAIL_ONLY and Config.PRINT_OTP_TO_CONSOLE:
            flash(
                "Development only: no email was sent. Use this code in step 2 "
                f"(expires in {OTP_EXPIRY_MINUTES} min): {otp}",
                "warning",
            )
        else:
            flash(
                "We sent a verification code to your email. Check your inbox and spam folder. "
                f"The code expires in {OTP_EXPIRY_MINUTES} minutes.",
                "success",
            )
        return redirect(url_for("login", tab="signup", next=next_raw or None))

    @app.route("/register/verify-otp", methods=["POST"])
    @limiter.limit("40/hour")
    def register_verify_otp():
        if session.get("user_id"):
            return redirect(url_for("index"))
        next_raw = request.form.get("next") or ""
        ok, err, email = validate_email(request.form.get("email") or "")
        otp = (request.form.get("otp") or "").strip().replace(" ", "")
        if not ok:
            flash(err or "Invalid email.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        if len(otp) < 4 or len(otp) > 10:
            flash("Enter the code from your email.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))

        db = SessionLocal()
        try:
            row = (
                db.query(SignupVerification)
                .filter(
                    SignupVerification.email == email,
                    SignupVerification.expires_at > datetime.utcnow(),
                )
                .order_by(SignupVerification.created_at.desc())
                .first()
            )
            if not row or not check_password_hash(row.otp_hash, otp):
                flash("Invalid or expired code. Request a new code.", "error")
                return redirect(url_for("login", tab="signup", next=next_raw or None))
            db.query(SignupVerification).filter(SignupVerification.email == email).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            logger.exception("register_verify_otp")
            db.rollback()
            flash("Verification failed. Try again.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        finally:
            db.close()

        session["signup_verified_email"] = email
        session["signup_verified_at"] = time.time()
        session["signup_pending_email"] = email
        flash("Email verified. Choose a password to finish.", "success")
        return redirect(url_for("login", tab="signup", next=next_raw or None))

    @app.route("/register/complete", methods=["POST"])
    @limiter.limit("15/hour")
    def register_complete():
        if session.get("user_id"):
            return redirect(url_for("index"))
        next_raw = request.form.get("next") or ""
        verified_email = session.get("signup_verified_email")
        verified_at = session.get("signup_verified_at")
        if (
            not verified_email
            or not verified_at
            or time.time() - float(verified_at) > SIGNUP_VERIFY_SESSION_SECONDS
        ):
            flash("Verification expired. Start again and request a new code.", "error")
            session.pop("signup_verified_email", None)
            session.pop("signup_verified_at", None)
            return redirect(url_for("login", tab="signup", next=next_raw or None))

        ok, err, email = validate_email(verified_email)
        if not ok or email != verified_email:
            session.pop("signup_verified_email", None)
            session.pop("signup_verified_at", None)
            flash("Invalid session. Start sign-up again.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))

        p1 = request.form.get("password") or ""
        p2 = request.form.get("password_confirm") or ""
        ok_p, err_p = validate_password(p1)
        if not ok_p:
            flash(err_p or "Invalid password.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        if p1 != p2:
            flash("Passwords do not match.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))

        db = SessionLocal()
        try:
            if _find_user_by_email(db, email):
                flash("An account with this email already exists. Sign in.", "error")
                session.pop("signup_verified_email", None)
                session.pop("signup_verified_at", None)
                return redirect(url_for("login", tab="user", next=next_raw or None))

            if db.query(User).filter(User.username == email).first():
                flash("That sign-in name is already taken.", "error")
                return redirect(url_for("login", tab="signup", next=next_raw or None))

            user = User(
                username=email,
                email=email,
                password_hash=generate_password_hash(p1),
                role=ROLE_GYAMA,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            _login_session(user)
        except Exception:
            logger.exception("register_complete")
            db.rollback()
            flash("Could not create account. Try again.", "error")
            return redirect(url_for("login", tab="signup", next=next_raw or None))
        finally:
            db.close()

        session.pop("signup_verified_email", None)
        session.pop("signup_verified_at", None)
        session.pop("signup_pending_email", None)
        flash("Account created. Welcome! Browse starter recipes to plan your first week.", "success")
        nxt = _safe_redirect_path(next_raw)
        if nxt:
            return redirect(nxt)
        return redirect(url_for("recipes"))

    def _is_env_admin_row(user: User) -> bool:
        admin_un = (Config.ADMIN_USERNAME or "admin").strip()
        return user.username == admin_un and getattr(user, "role", None) == ROLE_ADMIN

    def _verify_current_password_for_user(user: User, current: str) -> bool:
        """Accept env admin password or stored hash (after a prior password change)."""
        if not current:
            return False
        if _is_env_admin_row(user) and Config.ADMIN_PASSWORD and _ct_equal(current, Config.ADMIN_PASSWORD):
            return True
        return check_password_hash(user.password_hash, current)

    @app.route("/account/change-password", methods=["GET", "POST"])
    @limiter.limit("20/minute", methods=["POST"])
    def change_password():
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                session.clear()
                flash("Session invalid. Please sign in again.", "error")
                return redirect(url_for("login"))

            if request.method == "POST":
                current = request.form.get("current_password") or ""
                new_p = request.form.get("new_password") or ""
                confirm = request.form.get("new_password_confirm") or ""

                if not _verify_current_password_for_user(user, current):
                    flash("Current password is incorrect.", "error")
                    return render_template(
                        "change_password.html",
                        show_admin_password_hint=_is_env_admin_row(user),
                    )

                if new_p != confirm:
                    flash("New passwords do not match.", "error")
                    return render_template(
                        "change_password.html",
                        show_admin_password_hint=_is_env_admin_row(user),
                    )

                ok_p, err_p = validate_password(new_p)
                if not ok_p:
                    flash(err_p or "Invalid new password.", "error")
                    return render_template(
                        "change_password.html",
                        show_admin_password_hint=_is_env_admin_row(user),
                    )

                user.password_hash = generate_password_hash(new_p)
                db.commit()
                flash("Your password has been updated.", "success")
                return redirect(url_for("index"))

            return render_template(
                "change_password.html",
                show_admin_password_hint=_is_env_admin_row(user),
            )
        finally:
            db.close()

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))
