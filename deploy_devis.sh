#!/bin/bash
# ── Déploiement du module Devis & Factures sur PythonAnywhere ────────
# Exécuter dans la console Bash PythonAnywhere :
#   bash deploy_devis.sh

set -e
cd /home/donytchicaya/hellobiz

echo "📦 1. Migration de la base de données..."
python migrate_devis.py

echo ""
echo "🔄 2. Rechargement de l'application..."
touch /var/www/donytchicaya_pythonanywhere_com_wsgi.py

echo ""
echo "✅ Déploiement terminé !"
echo "   → https://donytchicaya.pythonanywhere.com/devis"
