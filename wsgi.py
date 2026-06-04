import sys
import os

# Chemin vers votre projet sur PythonAnywhere
# Remplacez "votre_username" par votre nom d'utilisateur PythonAnywhere
project_home = '/home/votre_username/hellobiz'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Dossier data pour la DB
os.makedirs(os.path.join(project_home, 'data'), exist_ok=True)
os.makedirs(os.path.join(project_home, 'static', 'uploads'), exist_ok=True)

from app import app as application
