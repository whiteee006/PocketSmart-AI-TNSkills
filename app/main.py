import os
from pathlib import Path

from fastapi import (
    FastAPI,
    Request,
    Form,
    File,
    UploadFile,
    HTTPException,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from app.services.auth_service import (
    register_user,
    authenticate_user,
    get_user_by_email,
    user_public,
)

from app.services.recommendation_service import (
    generate_home_recommendations,
    generate_party_recommendations,
    generate_jewelry_recommendations,
)

from app.services.history_service import (
    save_history,
    get_history,
)

from app.models.schemas import (
    HomePlannerInput,
    PartyPlannerInput,
    JewelryPlannerInput,
)


# ============================================================
# BASE CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="PocketSmart AI",
    version="1.0.0",
)


# ============================================================
# SESSION MIDDLEWARE
# ============================================================

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SESSION_SECRET",
        "change-this-secret",
    ),
    max_age=60 * 60 * 24 * 7,
)


# ============================================================
# STATIC FILES
# ============================================================

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)

app.mount(
    "/uploads",
    StaticFiles(directory=BASE_DIR / "static" / "uploads"),
    name="uploads",
)


# ============================================================
# JINJA TEMPLATES
# ============================================================

templates = Jinja2Templates(
    directory=BASE_DIR / "templates"
)


# ============================================================
# AUTHENTICATION HELPERS
# ============================================================

def current_user(request: Request):
    """
    Return the currently logged-in user.
    """
    email = request.session.get("user_email")

    if not email:
        return None

    return get_user_by_email(email)


def require_user(request: Request):
    """
    Require an authenticated user.
    """
    user = current_user(request)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    return user


# ============================================================
# HOME
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "user": current_user(request),
        },
    )


# ============================================================
# REGISTER PAGE
# ============================================================

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "request": request,
            "user": current_user(request),
        },
    )


# ============================================================
# REGISTER USER
# ============================================================

@app.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):

    clean_name = name.strip()
    clean_email = email.strip().lower()

    ok, message = register_user(
        clean_name,
        clean_email,
        password,
    )

    if not ok:

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "request": request,
                "error": message,
                "user": current_user(request),
            },
            status_code=400,
        )

    request.session["user_email"] = clean_email

    return RedirectResponse(
        "/dashboard",
        status_code=303,
    )


# ============================================================
# LOGIN PAGE
# ============================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "user": current_user(request),
        },
    )


# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):

    clean_email = email.strip().lower()

    user = authenticate_user(
        clean_email,
        password,
    )

    if not user:

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Invalid email or password.",
                "user": current_user(request),
            },
            status_code=401,
        )

    request.session["user_email"] = user["email"]

    return RedirectResponse(
        "/dashboard",
        status_code=303,
    )


# ============================================================
# LOGOUT
# ============================================================

@app.get("/logout")
async def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        "/login",
        status_code=303,
    )


# ============================================================
# TOKEN ROUTE
# ============================================================

@app.post("/token")
async def token(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):

    clean_email = email.strip().lower()

    user = authenticate_user(
        clean_email,
        password,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    request.session["user_email"] = user["email"]

    return {
        "access_token": user["email"],
        "token_type": "session",
    }


# ============================================================
# SESSION INFO
# ============================================================

@app.get("/session-info")
async def session_info(request: Request):

    user = current_user(request)

    return {
        "logged_in": bool(user),
        "user": user_public(user) if user else None,
    }


# ============================================================
# SESSION DATA
# ============================================================

@app.get("/session-data")
async def session_data(request: Request):

    user = require_user(request)

    return {
        "user": user_public(user),
        "history_count": len(
            get_history(user["email"])
        ),
    }


# ============================================================
# DASHBOARD
# ============================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):

    user = require_user(request)

    history = get_history(
        user["email"]
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "user": user,
            "history": history[-6:][::-1],
        },
    )


# ============================================================
# HOME PLANNER PAGE
# ============================================================

@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner(request: Request):

    user = require_user(request)

    return templates.TemplateResponse(
        request=request,
        name="home_planner.html",
        context={
            "request": request,
            "user": user,
        },
    )


# ============================================================
# PARTY PLANNER PAGE
# ============================================================

@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner(request: Request):

    user = require_user(request)

    return templates.TemplateResponse(
        request=request,
        name="party_planner.html",
        context={
            "request": request,
            "user": user,
        },
    )


# ============================================================
# JEWELRY PLANNER PAGE
# ============================================================

@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner(request: Request):

    user = require_user(request)

    return templates.TemplateResponse(
        request=request,
        name="jewelry_planner.html",
        context={
            "request": request,
            "user": user,
        },
    )


# ============================================================
# HOME RECOMMENDATIONS
# ============================================================

@app.post("/generate-home")
async def generate_home(request: Request):

    user = require_user(request)

    form = await request.form()

    data = HomePlannerInput(
        budget=float(
            form.get("budget", 0)
        ),
        room_type=str(
            form.get(
                "room_type",
                "Living Room",
            )
        ),
        quantity=int(
            form.get("quantity", 1)
        ),
        style=str(
            form.get(
                "style",
                "Modern",
            )
        ),
        needs=str(
            form.get("needs", "")
        ),
    )

    result = await generate_home_recommendations(
        data
    )

    save_history(
        user["email"],
        "Home",
        data.model_dump(),
        result,
    )

    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context={
            "request": request,
            "user": user,
            "category": "Home",
            "result": result,
            "input_data": data.model_dump(),
        },
    )


# ============================================================
# PARTY RECOMMENDATIONS
# ============================================================

@app.post("/generate-party")
async def generate_party(request: Request):

    user = require_user(request)

    form = await request.form()

    data = PartyPlannerInput(
        budget=float(
            form.get("budget", 0)
        ),
        guest_count=int(
            form.get("guest_count", 1)
        ),
        event_type=str(
            form.get(
                "event_type",
                "Birthday",
            )
        ),
        venue=str(
            form.get("venue", "")
        ),
        preferences=str(
            form.get("preferences", "")
        ),
    )

    result = await generate_party_recommendations(
        data
    )

    save_history(
        user["email"],
        "Party",
        data.model_dump(),
        result,
    )

    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context={
            "request": request,
            "user": user,
            "category": "Party",
            "result": result,
            "input_data": data.model_dump(),
        },
    )


# ============================================================
# JEWELRY RECOMMENDATIONS
# ============================================================

@app.post("/generate-jewelry")
async def generate_jewelry(
    request: Request,
    budget: float = Form(...),
    occasion: str = Form(...),
    style: str = Form(...),
    outfit_notes: str = Form(""),
    outfit_image: UploadFile | None = File(None),
):

    user = require_user(request)

    image_path = None

    # --------------------------------------------------------
    # OPTIONAL IMAGE UPLOAD
    # --------------------------------------------------------

    if outfit_image and outfit_image.filename:

        suffix = Path(
            outfit_image.filename
        ).suffix.lower()

        allowed_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }

        if suffix not in allowed_extensions:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Only JPG, PNG and WEBP "
                    "images are supported."
                ),
            )

        upload_dir = (
            BASE_DIR
            / "static"
            / "uploads"
        )

        upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        original_name = Path(
            outfit_image.filename
        ).name

        safe_name = (
            f"{user['id']}_"
            f"{original_name.replace(' ', '_')}"
        )

        image_path = upload_dir / safe_name

        image_path.write_bytes(
            await outfit_image.read()
        )

    # --------------------------------------------------------
    # JEWELRY INPUT
    # --------------------------------------------------------

    data = JewelryPlannerInput(
        budget=budget,
        occasion=occasion,
        style=style,
        outfit_notes=outfit_notes,
        image_path=(
            str(image_path)
            if image_path
            else None
        ),
    )

    # --------------------------------------------------------
    # GENERATE RECOMMENDATIONS
    # --------------------------------------------------------

    result = await generate_jewelry_recommendations(
        data
    )

    # --------------------------------------------------------
    # SAVE HISTORY
    # --------------------------------------------------------

    history_data = data.model_dump(
        exclude={"image_path"}
    )

    save_history(
        user["email"],
        "Jewelry",
        history_data,
        result,
    )

    # --------------------------------------------------------
    # SHOW RESULT
    # --------------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context={
            "request": request,
            "user": user,
            "category": "Jewelry",
            "result": result,
            "input_data": history_data,
        },
    )


# ============================================================
# LATEST RECOMMENDATION DETAILS
# ============================================================

@app.get("/recommendations-details")
async def recommendation_details(request: Request):

    user = require_user(request)

    history = get_history(
        user["email"]
    )

    if not history:

        return {
            "message": "No recommendations yet."
        }

    return history[-1]


# ============================================================
# HISTORY PAGE
# ============================================================

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):

    user = require_user(request)

    history = get_history(
        user["email"]
    )

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "request": request,
            "user": user,
            "history": history[::-1],
        },
    )


# ============================================================
# HISTORY API
# ============================================================

@app.get("/api/history")
async def history_api(request: Request):

    user = require_user(request)

    return {
        "items": get_history(
            user["email"]
        )[::-1]
    }


# ============================================================
# STARTUP STATUS
# ============================================================

@app.get("/startup")
async def startup_status():

    return {
        "status": "ok",
        "service": "PocketSmart AI",
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }