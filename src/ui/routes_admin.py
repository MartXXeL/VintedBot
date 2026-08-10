"""Panel de administración: los perfiles del resto del panel, su rol, si están
activos y qué suscripción tienen asignada — la única pantalla con visión de
todos los usuarios (el resto del panel se escopa siempre al propietario).
"""

from fastapi import APIRouter, Depends, Form, Request

from src.billing.plans import PLANS
from src.core.security import generate_random_password, hash_password
from src.core.users import User
from src.storage import users_store
from src.ui.deps import get_current_user, get_db_path, redirect_with_message, require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/admin")
def admin_users_view(
    request: Request, db_path: str = Depends(get_db_path), admin: User = Depends(get_current_user)
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "active": "admin",
            "current_user": admin,
            "users": users_store.list_users(db_path),
            "plans": PLANS,
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/users")
def create_user_route(
    email: str = Form(...),
    role: str = Form("member"),
    db_path: str = Depends(get_db_path),
):
    email = email.strip().lower()
    if not email:
        return redirect_with_message("/admin", error="Falta el email")
    if users_store.get_user_by_email(db_path, email) is not None:
        return redirect_with_message("/admin", error=f"Ya existe un usuario con el email {email}")

    role = role if role in ("admin", "member") else "member"
    password = generate_random_password()
    users_store.create_user(db_path, email, hash_password(password), role=role)
    return redirect_with_message(
        "/admin",
        ok=f"Usuario {email} creado ({role}). Contraseña (solo se muestra ahora): {password}",
    )


@router.post("/admin/users/{user_id}/role")
def set_role_route(
    user_id: int,
    role: str = Form(...),
    db_path: str = Depends(get_db_path),
    admin: User = Depends(get_current_user),
):
    target = users_store.get_user(db_path, user_id)
    if target is None:
        return redirect_with_message("/admin", error="Usuario no encontrado")
    if role not in ("admin", "member"):
        return redirect_with_message("/admin", error="Rol desconocido")
    if target.id == admin.id and role != "admin":
        return redirect_with_message("/admin", error="No puedes quitarte tu propio rol de administrador")

    users_store.set_role(db_path, user_id, role)
    return redirect_with_message("/admin", ok=f"{target.email} ahora es {role}")


@router.post("/admin/users/{user_id}/active")
def set_active_route(
    user_id: int,
    is_active: str = Form(None),
    db_path: str = Depends(get_db_path),
    admin: User = Depends(get_current_user),
):
    target = users_store.get_user(db_path, user_id)
    if target is None:
        return redirect_with_message("/admin", error="Usuario no encontrado")
    if target.id == admin.id and is_active is None:
        return redirect_with_message("/admin", error="No puedes desactivar tu propia cuenta")

    users_store.set_active(db_path, user_id, is_active is not None)
    estado = "activado" if is_active is not None else "desactivado"
    return redirect_with_message("/admin", ok=f"{target.email} {estado}")


@router.post("/admin/users/{user_id}/subscription")
def set_subscription_route(
    user_id: int,
    plan_id: str = Form(""),
    subscription_status: str = Form("none"),
    db_path: str = Depends(get_db_path),
):
    target = users_store.get_user(db_path, user_id)
    if target is None:
        return redirect_with_message("/admin", error="Usuario no encontrado")
    if plan_id and plan_id not in PLANS:
        return redirect_with_message("/admin", error="Plan desconocido")
    if subscription_status not in ("none", "active", "canceled", "past_due"):
        return redirect_with_message("/admin", error="Estado de suscripción desconocido")

    users_store.set_subscription(db_path, user_id, plan_id or None, subscription_status)
    return redirect_with_message("/admin", ok=f"Suscripción de {target.email} actualizada")


@router.post("/admin/users/{user_id}/reset-password")
def reset_password_route(
    user_id: int,
    db_path: str = Depends(get_db_path),
):
    target = users_store.get_user(db_path, user_id)
    if target is None:
        return redirect_with_message("/admin", error="Usuario no encontrado")

    password = generate_random_password()
    users_store.set_password_hash(db_path, user_id, hash_password(password))
    return redirect_with_message(
        "/admin", ok=f"Contraseña de {target.email} restablecida (solo se muestra ahora): {password}"
    )
