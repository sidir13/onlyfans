#!/usr/bin/env python
"""Script de lancement du dashboard Streamlit - Jumeaux Chauds.

Lance l interface graphique de monitoring et de commande des machines.
Le dashboard se connecte a l API FastAPI du simulateur.

Usage:
    python scripts/run_dashboard.py [OPTIONS]
    # ou directement:
    streamlit run dashboard/app.py

Options:
    --api-url    URL de l API FastAPI          [default: http://localhost:8000]
    --port       Port Streamlit                 [default: 8501]
    --host       Hote d ecoute                  [default: 0.0.0.0]
    --no-browser Ne pas ouvrir le navigateur

Exemples:
    python scripts/run_dashboard.py
    python scripts/run_dashboard.py --api-url http://localhost:8001
    python scripts/run_dashboard.py --port 8502 --no-browser

Pre-requis:
    Le simulateur doit etre demarre en premier:
    python scripts/run_simulator.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ajouter la racine du projet au PYTHONPATH
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DASHBOARD_APP = ROOT / "dashboard" / "app.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lancement du dashboard Streamlit - Jumeaux Chauds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_BASE_URL", "http://localhost:8000"),
        help="URL de l API FastAPI du simulateur [default: http://localhost:8000]",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("STREAMLIT_PORT", "8501")),
        help="Port d ecoute du dashboard Streamlit [default: 8501]",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("STREAMLIT_HOST", "0.0.0.0"),
        help="Hote d ecoute [default: 0.0.0.0]",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        default=os.getenv("NO_BROWSER", "false").lower() == "true",
        help="Ne pas ouvrir automatiquement le navigateur",
    )
    parser.add_argument(
        "--cluster",
        default=os.getenv("CLUSTER_ID", "cluster_alpha"),
        help="Cluster a monitorer [default: cluster_alpha]",
    )
    return parser.parse_args()


def check_streamlit() -> bool:
    """Verifier que streamlit est installe."""
    try:
        import streamlit  # noqa: F401
        return True
    except ImportError:
        return False


def check_dashboard_app() -> bool:
    """Verifier que le fichier app.py du dashboard existe."""
    return DASHBOARD_APP.exists()


def main() -> None:
    args = parse_args()

    # Verifier les pre-requis
    if not check_streamlit():
        print("[ERREUR] Streamlit non installe.")
        print("Lancer: pip install -r requirements.dashboard.txt")
        sys.exit(1)

    if not check_dashboard_app():
        print(f"[ERREUR] Fichier dashboard introuvable: {DASHBOARD_APP}")
        print("Le dossier dashboard/app.py sera cree en Phase 5 du developpement.")
        print("Pour l instant, le dashboard n est pas encore implemente.")
        sys.exit(1)

    # Configurer les variables d environnement pour le dashboard
    env = os.environ.copy()
    env["API_BASE_URL"] = args.api_url
    env["CLUSTER_ID"] = args.cluster

    # Construire la commande streamlit
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(DASHBOARD_APP),
        "--server.port", str(args.port),
        "--server.address", args.host,
        "--server.headless", "true" if args.no_browser else "false",
        "--theme.base", "dark",
        "--",
        "--api-url", args.api_url,
        "--cluster", args.cluster,
    ]

    print(f"Demarrage du dashboard Jumeaux Chauds")
    print(f"  API    : {args.api_url}")
    print(f"  Cluster: {args.cluster}")
    print(f"  URL    : http://localhost:{args.port}")
    print(f"  Appuyer sur Ctrl+C pour arreter\n")

    try:
        subprocess.run(cmd, env=env, check=True)
    except KeyboardInterrupt:
        print("\nDashboard arrete.")
    except subprocess.CalledProcessError as e:
        print(f"[ERREUR] Le dashboard a quitte avec le code {e.returncode}")
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("[ERREUR] Python ou streamlit introuvable dans le PATH.")
        sys.exit(1)


if __name__ == "__main__":
    main()
