# -*- coding: utf-8 -*-
# ==============================================================================
# Módulo: maintenance_advisor
# Descrição: Manutenção Preditiva com IA Explicável (XAI) para Indústria 4.0
# Compatibilidade: Odoo 19
# Dataset de Referência: AI4I 2020 Predictive Maintenance Dataset
# ==============================================================================

{
    'name': 'Maintenance Advisor — Predictive AI',
    'version': '19.0.1.0.0',
    'category': 'Maintenance',
    'summary': 'Manutenção preditiva com inteligência artificial e explicabilidade SHAP para Indústria 4.0.',
    'description': """
Maintenance Advisor — Predictive AI
=====================================
Módulo de Manutenção Preditiva com Inteligência Artificial Explicável (XAI)
desenvolvido para o ecossistema Odoo 19 e alinhado à filosofia da Indústria 4.0.

Funcionalidades Principais
---------------------------
* Coleta e armazenamento de telemetria de sensores (espelhando o AI4I 2020 Dataset).
* Motor de IA agnóstico por categoria de equipamento (roteador de modelos).
* Predição de falha via XGBoost (PoC com mock; pronto para modelo treinado real).
* Geração automática de gráficos SHAP (Shapley Additive Explanations) em base64.
* Criação automática de Ordens de Manutenção ao atingir limiar crítico de risco.
* Dashboard OWL para monitoramento em tempo real dos equipamentos.

Dataset de Referência (PoC)
----------------------------
AI4I 2020 Predictive Maintenance Dataset — simula leituras de fresadoras/CNC:
  - Air temperature [K]
  - Process temperature [K]
  - Rotational speed [rpm]
  - Torque [Nm]
  - Tool wear [min]
    """,
    'author': 'Paulo Mesquita',
    'website': 'https://github.com/paulomesquitas/maintenance-advisor-odoo-module',
    'license': 'MIT',

    # ------------------------------------------------------------------
    # Dependências: módulo nativo de manutenção + base do Odoo
    # ------------------------------------------------------------------
    'depends': [
        'base',
        'maintenance',
        'mail',           # Para chatter nas Ordens de Manutenção
        'web',            # Necessário para componentes OWL
    ],

    # ------------------------------------------------------------------
    # Dados carregados na instalação
    # ------------------------------------------------------------------
    'data': [
        # Segurança
        'security/ir.model.access.csv',

        # Views — Modelos
        'views/telemetry_views.xml',
        'views/equipment_views.xml',
        'views/prediction_wizard_views.xml',

        # Views — Menus e Ações
        'views/menu_views.xml',

        # Dados de configuração (CRON, parâmetros)
        'data/cron_jobs.xml',
        'data/system_parameters.xml',
    ],

    # ------------------------------------------------------------------
    # Assets Frontend (OWL / QWeb)
    # ------------------------------------------------------------------
    'assets': {
        'web.assets_backend': [
            # Componente OWL — Dashboard Preditivo
            'maintenance_advisor/static/src/components/predictive_dashboard.js',
            'maintenance_advisor/static/src/components/predictive_dashboard.xml',
            # Estilos customizados
            'maintenance_advisor/static/src/css/maintenance_advisor.css',
        ],
    },

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': True,

    # ------------------------------------------------------------------
    # Configurações de pós-instalação
    # ------------------------------------------------------------------
    'post_init_hook': 'post_init_hook',
}
