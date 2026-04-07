#!/usr/bin/env bash
# =============================================================
# install_deps.sh — Instala dependências do maintenance_advisor
# no ambiente Python correto do Odoo.
#
# USO:
#   chmod +x install_deps.sh
#   sudo bash install_deps.sh
#
# O script detecta automaticamente se o Odoo usa um virtualenv
# ou o Python do sistema, e instala no lugar certo.
# =============================================================

set -e

REQUIREMENTS="$(dirname "$0")/requirements.txt"
ODOO_CONFIG_PATHS=(
    "/etc/odoo/odoo.conf"
    "/etc/odoo19/odoo.conf"
    "/opt/odoo/odoo.conf"
    "/home/odoo/odoo.conf"
)

echo "========================================================"
echo " Maintenance Advisor — Instalador de Dependências Python"
echo "========================================================"

# ── 1. Detectar Python do Odoo ────────────────────────────────
PYTHON_BIN=""

# Tenta encontrar o virtualenv do Odoo pelos paths comuns
for VENV_PATH in /opt/odoo/venv /home/odoo/venv /odoo/venv /var/lib/odoo/venv; do
    if [ -f "$VENV_PATH/bin/pip" ]; then
        PYTHON_BIN="$VENV_PATH/bin/pip"
        echo "✅ Virtualenv Odoo detectado: $VENV_PATH"
        break
    fi
done

# Fallback: tenta encontrar o processo do Odoo em execução
if [ -z "$PYTHON_BIN" ]; then
    ODOO_PYTHON=$(ps aux | grep -E 'odoo-bin|odoo\.py' | grep -v grep | awk '{print $11}' | head -1)
    if [ -n "$ODOO_PYTHON" ]; then
        ODOO_DIR=$(dirname "$ODOO_PYTHON")
        if [ -f "$ODOO_DIR/pip" ]; then
            PYTHON_BIN="$ODOO_DIR/pip"
            echo "✅ Python Odoo detectado via processo: $PYTHON_BIN"
        fi
    fi
fi

# Fallback final: pip3 do sistema
if [ -z "$PYTHON_BIN" ]; then
    echo "⚠️  Virtualenv do Odoo não encontrado. Usando pip3 do sistema."
    echo "   Se o Odoo usa um venv específico, passe o caminho manualmente:"
    echo "   sudo /caminho/para/venv/bin/pip install -r $REQUIREMENTS"
    PYTHON_BIN="pip3"
fi

# ── 2. Instalar as dependências ───────────────────────────────
echo ""
echo "📦 Instalando dependências de: $REQUIREMENTS"
echo "   Usando: $PYTHON_BIN"
echo ""

if [ "$PYTHON_BIN" = "pip3" ]; then
    # Sistema sem venv — pode precisar do flag
    $PYTHON_BIN install -r "$REQUIREMENTS" --break-system-packages 2>/dev/null \
        || $PYTHON_BIN install -r "$REQUIREMENTS"
else
    $PYTHON_BIN install -r "$REQUIREMENTS"
fi

# ── 3. Verificar instalação ───────────────────────────────────
echo ""
echo "🔍 Verificando pacotes instalados..."
PYTHON_CHECK="${PYTHON_BIN/pip/python}"
[ "$PYTHON_BIN" = "pip3" ] && PYTHON_CHECK="python3"

$PYTHON_CHECK -c "
import importlib, sys
packages = ['numpy', 'pandas', 'matplotlib', 'sklearn', 'xgboost', 'shap', 'joblib']
all_ok = True
for pkg in packages:
    try:
        m = importlib.import_module(pkg)
        ver = getattr(m, '__version__', '?')
        print(f'  ✅ {pkg:<15} {ver}')
    except ImportError:
        print(f'  ❌ {pkg:<15} NÃO INSTALADO')
        all_ok = False
sys.exit(0 if all_ok else 1)
" && echo "" && echo "✅ Todas as dependências instaladas com sucesso!" \
  || { echo ""; echo "❌ Algumas dependências falharam. Verifique os erros acima."; exit 1; }

echo ""
echo "👉 Próximos passos:"
echo "   1. Reinicie o servidor Odoo: sudo systemctl restart odoo"
echo "   2. Instale/atualize o módulo: Configurações → Apps → maintenance_advisor"
echo "========================================================"
