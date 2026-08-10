"""Tutorial: una sola pantalla que explica todo el funcionamiento del panel.

Sin lógica que probar más allá de "la página carga" — es contenido, vive
entero en `tutorial.html`. Aparte de servir de ayuda dentro de la propia
app, es el sitio donde señalar explícitamente los límites y avisos
importantes (ritmo seguro, DAC7, aprobación humana) en un lenguaje más
cercano que el README.
"""

from fastapi import APIRouter, Depends, Request

from src.core.users import User
from src.ui.deps import get_current_user, require_login

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/tutorial")
def tutorial_view(request: Request, user: User = Depends(get_current_user)):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "tutorial.html", {"active": "tutorial", "current_user": user})
