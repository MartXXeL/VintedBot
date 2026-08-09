"""Punto de entrada: carga `.env`, prepara la app y levanta el panel.

El trabajador en segundo plano (`src/worker/scheduler.py`) no es un proceso
aparte: arranca y para con el ciclo de vida de la propia app FastAPI (ver
`src/ui/app.py::create_app`), así que un único `python -m src.main` basta
para tener panel + automatización funcionando.
"""

import uvicorn
from dotenv import load_dotenv

from src.core.settings import load_settings
from src.ui.app import create_app


def main() -> None:
    load_dotenv()
    settings = load_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.dashboard_host, port=settings.dashboard_port)


if __name__ == "__main__":
    main()
