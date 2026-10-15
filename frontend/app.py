"""Flask frontend (server-rendered Jinja templates) for the FastAPI expense tracker.

Flow: browser -> Flask (HTML, forms, session cookie holding the JWT) -> FastAPI (JSON API).
Replaces the old Alpine.js single-page UI: every action is a normal HTML form
(POST -> redirect -> GET), so it works without client-side JavaScript.
"""
import os
import secrets
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.middleware.proxy_fix import ProxyFix

from api_client import ApiClient, ApiError

load_dotenv()  # read frontend/.env for local development (real env vars still win)

CATEGORIES = ["food", "transport", "housing", "utilities", "health", "entertainment", "shopping", "education", "other"]
SORTS = {
    "newest": "Recently added",
    "date_desc": "Date, newest first",
    "date_asc": "Date, oldest first",
    "amount_desc": "Amount, high to low",
    "amount_asc": "Amount, low to high",
}
CURRENCIES = ["USD", "EUR", "GBP", "PKR", "INR", "AED", "SAR", "CAD", "AUD"]
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "PKR": "Rs ", "CAD": "CA$", "AUD": "A$"}


def create_app(api_factory=None) -> Flask:
    """App factory. Tests pass `api_factory` to swap the real API client for a fake."""
    app = Flask(__name__)

    env = os.getenv("ENVIRONMENT", "development")
    secret = os.getenv("SECRET_KEY")
    if not secret:
        if env == "production":
            raise RuntimeError("SECRET_KEY must be set in production")
        secret = "dev-only-secret-change-me"
    api_url = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
    public_api_url = os.getenv("API_PUBLIC_URL", api_url).rstrip("/")

    app.config.update(
        SECRET_KEY=secret,
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,  # reject huge uploads before they reach the API
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(env == "production"),
    )
    make_api = api_factory or (lambda token=None, client_ip=None: ApiClient(api_url, token, client_ip))
    if env == "production":
        # Behind Render's proxy: trust ONE hop of X-Forwarded-* so request.remote_addr is the real visitor.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ------------------------------------------------------------ helpers
    @app.before_request
    def csrf_protect() -> None:
        """Every POST must carry the per-session token that our forms embed."""
        if request.method == "POST":
            sent = request.form.get("_csrf", "")
            if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
                abort(400, "Your form expired. Go back, refresh the page and try again.")

    @app.before_request
    def attach_api() -> None:
        g.api = make_api(session.get("token"), request.remote_addr)

    @app.template_global()
    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals.update(CATEGORIES=CATEGORIES, CURRENCIES=CURRENCIES)

    @app.context_processor
    def inject_globals() -> dict:
        return {"user_name": session.get("name"), "api_docs_url": f"{public_api_url}/docs"}

    def login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("token"):
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapper

    def back_to_dashboard() -> Response:
        """Redirect to where the user came from (same-site only), else the dashboard."""
        ref = request.referrer
        if ref and urlparse(ref).netloc == request.host:
            return redirect(ref)
        return redirect(url_for("dashboard"))

    # ---------------------------------------------------------- filters
    @app.template_filter("money")
    def money(value, currency: str = "USD") -> str:
        symbol = SYMBOLS.get(currency, f"{currency} ")
        return f"{symbol}{float(value or 0):,.2f}"

    @app.template_filter("short_date")
    def short_date(value: str) -> str:
        return date.fromisoformat(value).strftime("%d %b %Y")

    @app.template_filter("short_dt")
    def short_dt(value: str) -> str:
        return datetime.fromisoformat(value).strftime("%d %b, %H:%M")

    @app.template_filter("month_label")
    def month_label(value: str) -> str:
        return datetime.strptime(value, "%Y-%m").strftime("%B %Y")

    @app.template_filter("label")
    def label(value: str) -> str:
        return value.replace("_", " ").capitalize()

    @app.template_global()
    def page_url(page: int) -> str:
        args = request.args.to_dict()
        args["page"] = page
        return url_for("dashboard", **args)

    @app.template_global()
    def receipt_href(path: str) -> str:
        return f"{public_api_url}{path}"

    # ------------------------------------------------------ error pages
    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        if err.status_code == 401:  # expired/invalid JWT
            session.clear()
            flash("Your session expired. Please log in again.", "error")
            return redirect(url_for("login"))
        return render_template("error.html", status=err.status_code, message=err.message), err.status_code

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def handle_http_error(err):
        message = {413: "That file is too large (6 MB max)."}.get(err.code, err.description)
        return render_template("error.html", status=err.code, message=message), err.code

    # -------------------------------------------------------------- auth
    @app.get("/")
    def index():
        return redirect(url_for("dashboard" if session.get("token") else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            try:
                g.api.register(email, request.form.get("full_name", "").strip(), request.form.get("password", ""))
                token = g.api.login(email, request.form.get("password", ""))
            except ApiError as err:
                flash(err.message, "error")
                return render_template("register.html", form=request.form), 400
            start_session(token, request.form.get("full_name", "").strip())
            flash("Welcome aboard. Add your first expense below.", "success")
            return redirect(url_for("dashboard"))
        return render_template("register.html", form={})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            try:
                token = g.api.login(email, request.form.get("password", ""))
                name = make_api(token, request.remote_addr).me()["full_name"]
            except ApiError as err:
                flash(err.message, "error")
                return render_template("login.html", form=request.form), 401 if err.status_code == 401 else 400
            start_session(token, name)
            return redirect(url_for("dashboard"))
        return render_template("login.html", form={})

    def start_session(token: str, name: str) -> None:
        session.clear()  # new session id/CSRF token after login (prevents session fixation)
        session["token"] = token
        session["name"] = name

    @app.post("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    # --------------------------------------------------------- dashboard
    @app.get("/dashboard")
    @login_required
    def dashboard():
        keys = ("q", "category", "status", "sort", "min_amount", "max_amount", "date_from", "date_to", "page", "page_size")
        params = {k: request.args[k] for k in keys if request.args.get(k)}
        params.setdefault("page_size", "10")
        month = request.args.get("month") or None

        page = g.api.list_expenses(params)
        stats = g.api.stats(month)
        activity = g.api.activity()

        budget = float(stats["monthly_budget"]) or 1.0
        paid_pct = min(100.0, float(stats["paid_total"]) / budget * 100)
        pending_pct = max(0.0, min(100.0 - paid_pct, float(stats["pending_total"]) / budget * 100))
        top_category = float(stats["by_category"][0]["total"]) if stats["by_category"] else 1.0
        return render_template(
            "dashboard.html",
            page=page,
            stats=stats,
            activity=activity,
            paid_pct=paid_pct,
            pending_pct=pending_pct,
            top_category=top_category or 1.0,
            remaining=float(stats["monthly_budget"]) - float(stats["total_spent"]),
            filters=request.args,
            sorts=SORTS,
            today=date.today().isoformat(),
        )

    @app.post("/settings")
    @login_required
    def update_settings():
        try:
            g.api.update_me(monthly_budget=request.form.get("monthly_budget", ""), currency=request.form.get("currency", "USD"))
            flash("Budget updated.", "success")
        except ApiError as err:
            flash(err.message, "error")
        return back_to_dashboard()

    # ---------------------------------------------------------- expenses
    def expense_payload() -> dict:
        data = {
            "title": request.form.get("title", ""),
            "amount": request.form.get("amount", ""),
            "category": request.form.get("category", "other"),
            "status": request.form.get("status", "pending"),
            "expense_date": request.form.get("expense_date") or date.today().isoformat(),
            "notes": request.form.get("notes", "").strip() or None,
        }
        return data

    @app.post("/expenses")
    @login_required
    def create_expense():
        try:
            created = g.api.create_expense(expense_payload())
            flash(f"Added “{created['title']}”.", "success")
        except ApiError as err:
            flash(err.message, "error")
        return back_to_dashboard()

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_expense(expense_id: int):
        if request.method == "POST":
            try:
                g.api.update_expense(expense_id, expense_payload())
                flash("Changes saved.", "success")
                return redirect(url_for("dashboard"))
            except ApiError as err:
                flash(err.message, "error")
                return redirect(url_for("edit_expense", expense_id=expense_id))
        return render_template("edit.html", expense=g.api.get_expense(expense_id))

    @app.post("/expenses/<int:expense_id>/toggle")
    @login_required
    def toggle_expense(expense_id: int):
        try:
            g.api.toggle_expense(expense_id)
        except ApiError as err:
            flash(err.message, "error")
        return back_to_dashboard()

    @app.post("/expenses/<int:expense_id>/delete")
    @login_required
    def delete_expense(expense_id: int):
        try:
            g.api.delete_expense(expense_id)
            flash("Expense deleted.", "success")
        except ApiError as err:
            flash(err.message, "error")
        return back_to_dashboard()

    @app.post("/expenses/<int:expense_id>/receipt")
    @login_required
    def upload_receipt(expense_id: int):
        file = request.files.get("receipt")
        if not file or not file.filename:
            flash("Choose a file first.", "error")
        else:
            try:
                g.api.upload_receipt(expense_id, file.filename, file.read(), file.mimetype)
                flash("Receipt attached.", "success")
            except ApiError as err:
                flash(err.message, "error")
        return redirect(url_for("edit_expense", expense_id=expense_id))

    @app.get("/export.csv")
    @login_required
    def export_csv():
        return Response(
            g.api.export_csv(),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="expenses.csv"'},
        )

    # ------------------------------------------------------------- tools
    @app.route("/tools", methods=["GET", "POST"])
    @login_required
    def tools():
        me = g.api.me()
        ctx: dict = {"currency": me["currency"], "rates": None, "rates_error": None, "converted": None,
                     "convert_error": None, "crawl_results": None, "urls_text": ""}

        if request.method == "POST":  # web crawler form
            ctx["urls_text"] = request.form.get("urls", "")
            urls = [u.strip() for u in ctx["urls_text"].splitlines() if u.strip()][:5]
            if not urls:
                flash("Paste at least one URL.", "error")
            else:
                try:
                    ctx["crawl_results"] = g.api.crawl(urls)
                except ApiError as err:
                    flash(err.message, "error")

        try:
            symbols = ",".join(c for c in CURRENCIES if c != me["currency"])
            ctx["rates"] = g.api.rates(me["currency"], symbols)
        except ApiError as err:
            if err.status_code == 401:
                raise
            ctx["rates_error"] = err.message

        if request.args.get("amount"):
            try:
                ctx["converted"] = g.api.convert(
                    request.args["amount"], request.args.get("from", me["currency"]), request.args.get("to", "EUR")
                )
            except ApiError as err:
                if err.status_code == 401:
                    raise
                ctx["convert_error"] = err.message
        return render_template("tools.html", **ctx)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
