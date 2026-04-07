# -*- coding: utf-8 -*-
# ==============================================================================
# Motor de IA — Manutenção Preditiva com XAI (Explicabilidade via SHAP)
#
# Arquitetura:
#   AIRouter  ──►  AIEngine (por categoria)  ──►  SHAPExplainer
#
# Este arquivo contém:
#   1. AIEngine     — Motor de predição (mock XGBoost para PoC / stub para modelo real).
#   2. SHAPExplainer — Geração do gráfico e texto de explicabilidade.
#   3. AIRouter     — Roteador agnóstico que despacha para o engine correto.
#
# Para substituir o mock por um modelo real treinado:
#   1. Salve o modelo com: joblib.dump(xgb_model, 'milling_model.joblib')
#   2. Coloque o arquivo em: maintenance_advisor/static/models/
#   3. Mude MOCK_MODE = False em MillingAIEngine.
# ==============================================================================

import io
import base64
import logging
import random
import math
from typing import Dict, Any, Optional, Tuple

_logger = logging.getLogger(__name__)

# ==============================================================================
# IMPORTAÇÕES LAZY — Bibliotecas científicas são carregadas apenas quando
# necessárias (na primeira predição), e NÃO durante a instalação do módulo.
# Isso evita o ModuleNotFoundError no momento do `odoo -u maintenance_advisor`.
# ==============================================================================

def _require_numpy():
    """Importa numpy; lança erro amigável se não instalado."""
    try:
        import numpy as _np
        return _np
    except ImportError:
        raise ImportError(
            "[maintenance_advisor] numpy não encontrado.\n"
            "Execute: pip install numpy pandas matplotlib scikit-learn xgboost shap"
        )

def _require_pandas():
    try:
        import pandas as _pd
        return _pd
    except ImportError:
        raise ImportError(
            "[maintenance_advisor] pandas não encontrado.\n"
            "Execute: pip install numpy pandas matplotlib scikit-learn xgboost shap"
        )

def _require_matplotlib():
    """Importa matplotlib configurando o backend Agg (sem GUI)."""
    try:
        import matplotlib as _mpl
        _mpl.use('Agg')
        import matplotlib.pyplot as _plt
        import matplotlib.patches as _mpatches
        return _mpl, _plt, _mpatches
    except ImportError:
        raise ImportError(
            "[maintenance_advisor] matplotlib não encontrado.\n"
            "Execute: pip install numpy pandas matplotlib scikit-learn xgboost shap"
        )

# Aliases usados internamente — resolvidos de forma lazy
def _np():
    return _require_numpy()

def _pd():
    return _require_pandas()

# ------------------------------------------------------------------
# CONSTANTES GLOBAIS
# ------------------------------------------------------------------

# Nomes das features na mesma ordem esperada pelo modelo AI4I 2020
AI4I_FEATURE_NAMES = [
    'Air temperature [K]',
    'Process temperature [K]',
    'Rotational speed [rpm]',
    'Torque [Nm]',
    'Tool wear [min]',
]

# Cores do tema visual do módulo
COLOR_CRITICAL  = '#E74C3C'   # Vermelho — risco crítico
COLOR_WARNING   = '#F39C12'   # Laranja — risco moderado
COLOR_SAFE      = '#27AE60'   # Verde — risco baixo
COLOR_NEUTRAL   = '#2C3E50'   # Azul escuro — texto padrão
COLOR_BAR_POS   = '#E74C3C'   # Barras positivas SHAP (aumentam risco)
COLOR_BAR_NEG   = '#27AE60'   # Barras negativas SHAP (reduzem risco)


# ==============================================================================
# 1. MOTOR BASE (Interface)
# ==============================================================================

class BaseAIEngine:
    """
    Interface base para todos os motores de IA do módulo.
    Cada categoria de equipamento deve herdar desta classe e implementar `predict`.
    """

    FEATURE_NAMES: list = []
    ENGINE_VERSION: str = 'base-0.0'

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Executa a predição de risco de falha.

        Args:
            features: Dicionário {nome_feature: valor} com as leituras do sensor.

        Returns:
            dict com chaves:
                - failure_probability (float): Probabilidade 0.0–100.0 (em %)
                - raw_score           (float): Score bruto do modelo (ex: log-odds ou proba 0–1)
                - model_version       (str):   Versão do modelo utilizado
                - shap_values         (list):  Valores SHAP para cada feature (ou None)
                - feature_values      (dict):  Valores normalizados passados ao modelo
        """
        raise NotImplementedError("Subclasses devem implementar o método `predict`.")

    def _validate_features(self, features: Dict[str, float]):
        """
        Valida e converte o dicionário de features para um DataFrame Pandas.
        Preenche com 0.0 features ausentes (com log de aviso).
        """
        pd = _require_pandas()
        row = {}
        for fname in self.FEATURE_NAMES:
            if fname not in features:
                _logger.warning("Feature ausente: '%s'. Usando 0.0 como fallback.", fname)
                row[fname] = 0.0
            else:
                row[fname] = float(features[fname])
        return pd.DataFrame([row], columns=self.FEATURE_NAMES)


# ==============================================================================
# 2. ENGINE PARA FRESADORA / CNC (AI4I 2020 — Mock XGBoost)
# ==============================================================================

class MillingAIEngine(BaseAIEngine):
    """
    Motor de predição para Fresadoras e Máquinas CNC.
    Dataset de referência: AI4I 2020 Predictive Maintenance Dataset.

    Modo atual: MOCK (PoC)
    ─────────────────────────────────────────────────────────────────
    O modelo mock implementa uma heurística baseada nas distribuições
    do AI4I 2020, simulando o comportamento esperado de um XGBoost real:
      - Tool wear > 200 min → contribuição alta para falha
      - Torque > 60 Nm      → contribuição alta para falha
      - ΔT (processo - ar) muito baixo ou muito alto → anomalia
      - RPM extremamente baixo → indicativo de falha mecânica

    Para ativar o modelo real XGBoost:
      Veja as instruções no topo deste arquivo (MOCK_MODE = False).
    """

    FEATURE_NAMES  = AI4I_FEATURE_NAMES
    ENGINE_VERSION = 'milling-mock-v0.1'
    MOCK_MODE      = False  # Mude para False ao integrar modelo treinado real

    # Pesos heurísticos para o mock — baseados em análise exploratória do AI4I
    _MOCK_WEIGHTS = {
        'Air temperature [K]':     0.05,
        'Process temperature [K]': 0.08,
        'Rotational speed [rpm]':  0.12,
        'Torque [Nm]':             0.35,   # Alta importância no dataset real
        'Tool wear [min]':         0.40,   # Maior importância no dataset real
    }

    def __init__(self):
        self._model = None
        if not self.MOCK_MODE:
            self._load_model()

    def _load_model(self):
        """Carrega modelo XGBoost serializado (somente quando MOCK_MODE=False)."""
        try:
            import joblib
            import os
            model_path = os.path.join(
                os.path.dirname(__file__), '..', 'static', 'models', 'milling_xgboost.joblib'
            )
            model_path = os.path.normpath(model_path)
            _logger.info("[AI] Tentando carregar modelo em: %s", model_path)
            _logger.info("[AI] Arquivo existe: %s", os.path.exists(model_path))
            self._model = joblib.load(model_path)
            _logger.info("[AI] Modelo XGBoost carregado com sucesso!")
        except Exception as e:
            import traceback
            _logger.error("[AI] Falha ao carregar modelo XGBoost: %s", e)
            _logger.error("[AI] Traceback completo: %s", traceback.format_exc())
            self.MOCK_MODE = True

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Executa predição de risco de falha para fresadora/CNC."""
        df = self._validate_features(features)

        if self.MOCK_MODE:
            return self._mock_predict(df)
        else:
            return self._xgboost_predict(df)

    def _mock_predict(self, df) -> Dict[str, Any]:
        """
        Predição heurística (mock) baseada nas distribuições do AI4I 2020.

        Lógica de scoring:
          score = Σ (peso_i × normalizado_i) + ruído_gaussiano_pequeno

        Normalização por feature:
          - tool_wear_min:         score máximo quando ≥ 250 min
          - torque_nm:             score máximo quando ≥ 70 Nm
          - rotational_speed_rpm:  score alto quando < 1300 rpm (instabilidade)
          - temp_delta:            score alto quando ΔT < 5 K ou > 15 K (anomalia)
        """
        row = df.iloc[0]

        # Normalização 0–1 por feature
        tool_wear_norm = min(row['Tool wear [min]'] / 250.0, 1.0)
        torque_norm    = min(row['Torque [Nm]'] / 70.0, 1.0)

        # RPM: risco aumenta quando RPM cai abaixo de 1400 OU sobe acima de 2886
        rpm = row['Rotational speed [rpm]']
        if rpm < 1400:
            rpm_norm = min((1400 - rpm) / 300.0, 1.0)
        elif rpm > 2886:
            rpm_norm = min((rpm - 2886) / 500.0, 1.0)
        else:
            rpm_norm = 0.0

        # Temperatura: combina ΔT anômalo + T.Proc absoluta acima do normal (> 314 K)
        delta_t = row['Process temperature [K]'] - row['Air temperature [K]']
        if delta_t < 5:
            temp_norm_delta = min((5 - delta_t) / 5.0, 1.0)
        elif delta_t > 15:
            temp_norm_delta = min((delta_t - 15) / 10.0, 1.0)
        else:
            temp_norm_delta = 0.0

        t_proc_abs = row['Process temperature [K]']
        temp_norm_abs = min(max(0.0, (t_proc_abs - 314.0) / 10.0), 1.0)
        temp_norm = max(temp_norm_delta, temp_norm_abs)

        # Score ponderado
        raw_score = (
            self._MOCK_WEIGHTS['Tool wear [min]']         * tool_wear_norm +
            self._MOCK_WEIGHTS['Torque [Nm]']             * torque_norm +
            self._MOCK_WEIGHTS['Rotational speed [rpm]']  * rpm_norm +
            self._MOCK_WEIGHTS['Process temperature [K]'] * temp_norm
        )

        # Pequeno ruído gaussiano para simular variabilidade do modelo
        noise = random.gauss(0, 0.02)
        raw_score = max(0.0, min(1.0, raw_score + noise))

        failure_probability = round(raw_score * 100.0, 2)

        # Valores SHAP simulados: proporcionais ao peso × normalização de cada feature
        shap_values = [
            round(self._MOCK_WEIGHTS['Air temperature [K]']     * (temp_norm * 0.3), 4),
            round(self._MOCK_WEIGHTS['Process temperature [K]'] * temp_norm, 4),
            round(self._MOCK_WEIGHTS['Rotational speed [rpm]']  * rpm_norm, 4),
            round(self._MOCK_WEIGHTS['Torque [Nm]']             * torque_norm, 4),
            round(self._MOCK_WEIGHTS['Tool wear [min]']         * tool_wear_norm, 4),
        ]

        _logger.debug(
            "[MockEngine] Predição: %.2f%% | tool_wear=%.0f | torque=%.1f | rpm=%.0f | ΔT=%.1f",
            failure_probability,
            row['Tool wear [min]'], row['Torque [Nm]'],
            row['Rotational speed [rpm]'], delta_t
        )

        return {
            'failure_probability': failure_probability,
            'raw_score':           raw_score,
            'model_version':       self.ENGINE_VERSION,
            'shap_values':         shap_values,
            'feature_values':      df.iloc[0].to_dict(),
            'mock_mode':           True,
        }

    def _xgboost_predict(self, df) -> Dict[str, Any]:
        try:
            import shap as shap_lib

            _NAME_MAP = {
                'Air temperature [K]':     'Air_temperature_K',
                'Process temperature [K]': 'Process_temperature_K',
                'Rotational speed [rpm]':  'Rotational_speed_rpm',
                'Torque [Nm]':             'Torque_Nm',
                'Tool wear [min]':         'Tool_wear_min',
            }
            df_xgb = df.rename(columns=_NAME_MAP)

            proba = self._model.predict_proba(df_xgb)[0][1]
            failure_probability = round(proba * 100.0, 2)

            explainer   = shap_lib.TreeExplainer(self._model)
            shap_matrix = explainer.shap_values(df_xgb)

            if isinstance(shap_matrix, list):
                shap_values = shap_matrix[1][0].tolist()
            else:
                shap_values = shap_matrix[0].tolist()

            return {
                'failure_probability': failure_probability,
                'raw_score':           float(proba),
                'model_version':       'xgboost-ai4i-v1.1',
                'shap_values':         shap_values,
                'feature_values':      df.iloc[0].to_dict(),
                'mock_mode':           False,
            }
        except Exception as e:
            import traceback
            _logger.error("[AI] Erro na predicao XGBoost real: %s", e)
            _logger.error("[AI] Traceback: %s", traceback.format_exc())
            return self._mock_predict(df)


# ==============================================================================
# 3. STUBS PARA OUTRAS CATEGORIAS (prontos para expansão futura)
# ==============================================================================

class CompressorAIEngine(BaseAIEngine):
    """Motor stub para compressores. Substitua por modelo dedicado."""

    ENGINE_VERSION = 'compressor-stub-v0.1'
    FEATURE_NAMES  = [
        'Suction Pressure [bar]',
        'Discharge Pressure [bar]',
        'Oil Temperature [°C]',
        'Vibration [mm/s]',
        'Operating Hours [h]',
    ]

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        _logger.warning("CompressorAIEngine está em modo stub. Retornando predição aleatória.")
        proba = random.uniform(0.05, 0.95)
        return {
            'failure_probability': round(proba * 100, 2),
            'raw_score':           proba,
            'model_version':       self.ENGINE_VERSION,
            'shap_values':         [random.uniform(-0.1, 0.3) for _ in self.FEATURE_NAMES],
            'feature_values':      features,
            'mock_mode':           True,
        }


class ConveyorAIEngine(BaseAIEngine):
    """Motor stub para esteiras transportadoras."""

    ENGINE_VERSION = 'conveyor-stub-v0.1'
    FEATURE_NAMES  = ['Belt Speed [m/s]', 'Load [kg]', 'Belt Tension [N]', 'Vibration [mm/s]']

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        proba = random.uniform(0.05, 0.60)
        return {
            'failure_probability': round(proba * 100, 2),
            'raw_score':           proba,
            'model_version':       self.ENGINE_VERSION,
            'shap_values':         [random.uniform(-0.05, 0.2) for _ in self.FEATURE_NAMES],
            'feature_values':      features,
            'mock_mode':           True,
        }


# ==============================================================================
# 4. EXPLICADOR SHAP — Geração de Gráfico e Texto
# ==============================================================================

class SHAPExplainer:
    """
    Gera gráficos de barras SHAP e explicações textuais para uma predição.

    Uso:
        explainer = SHAPExplainer()
        chart_b64, explanation_html, top_feature = explainer.explain(
            shap_values=[0.12, 0.03, 0.08, 0.25, 0.35],
            feature_names=AI4I_FEATURE_NAMES,
            feature_values={'Tool wear [min]': 215, ...},
            failure_probability=82.5
        )
    """

    def explain(
        self,
        shap_values:         list,
        feature_names:       list,
        feature_values:      Dict[str, float],
        failure_probability: float,
    ) -> Tuple[str, str, str]:
        """
        Gera o gráfico SHAP e o texto explicativo.

        Returns:
            Tuple[chart_b64, explanation_html, top_feature_name]
        """
        chart_b64    = self._generate_shap_chart(shap_values, feature_names, feature_values, failure_probability)
        top_feature  = self._get_top_feature(shap_values, feature_names)
        explanation  = self._generate_explanation_html(shap_values, feature_names, feature_values, failure_probability, top_feature)
        return chart_b64, explanation, top_feature

    def _generate_shap_chart(
        self,
        shap_values:         list,
        feature_names:       list,
        feature_values:      Dict[str, float],
        failure_probability: float,
    ) -> str:
        """
        Gera um gráfico de barras horizontais SHAP estilizado e retorna em Base64 (PNG).

        O gráfico segue o padrão de visualização SHAP:
          - Barras vermelhas → features que AUMENTAM o risco
          - Barras verdes    → features que REDUZEM o risco
          - Ordenadas por valor absoluto (maior impacto no topo)
        """
        # Importações lazy — só carrega matplotlib quando realmente precisar gerar o gráfico
        _mpl, plt, mpatches = _require_matplotlib()

        # Ordenar por valor absoluto (descendente)
        sorted_pairs = sorted(
            zip(feature_names, shap_values, [feature_values.get(f, 0) for f in feature_names]),
            key=lambda x: abs(x[1]),
            reverse=True
        )
        s_names, s_shap, s_vals = zip(*sorted_pairs) if sorted_pairs else ([], [], [])

        fig, ax = plt.subplots(figsize=(9, max(4, len(s_names) * 0.9)))
        fig.patch.set_facecolor('#1A1A2E')
        ax.set_facecolor('#16213E')

        colors = [COLOR_BAR_POS if v >= 0 else COLOR_BAR_NEG for v in s_shap]
        bars   = ax.barh(range(len(s_names)), s_shap, color=colors, edgecolor='none', height=0.6)

        # Rótulos dos eixos Y com valor atual da feature
        y_labels = [
            f"{name}\n(valor: {val:.1f})"
            for name, val in zip(s_names, s_vals)
        ]
        ax.set_yticks(range(len(s_names)))
        ax.set_yticklabels(y_labels, color='#ECF0F1', fontsize=9)
        ax.tick_params(axis='x', colors='#ECF0F1', labelsize=8)

        # Valores nas barras
        for i, (bar, val) in enumerate(zip(bars, s_shap)):
            sign = '+' if val >= 0 else ''
            ax.text(
                val + (0.003 if val >= 0 else -0.003),
                i,
                f'{sign}{val:.3f}',
                va='center',
                ha='left' if val >= 0 else 'right',
                color='#ECF0F1',
                fontsize=8,
                fontweight='bold',
            )

        # Linha de base (zero)
        ax.axvline(x=0, color='#7F8C8D', linewidth=1.5, linestyle='--', alpha=0.7)

        # Título e labels
        risk_color = COLOR_CRITICAL if failure_probability >= 70 else (
            COLOR_WARNING if failure_probability >= 40 else COLOR_SAFE
        )
        ax.set_title(
            f'Explicação SHAP da Predição\n'
            f'Risco de Falha: {failure_probability:.1f}%',
            color=risk_color,
            fontsize=12,
            fontweight='bold',
            pad=12,
        )
        ax.set_xlabel('Contribuição SHAP (impacto no risco de falha)', color='#BDC3C7', fontsize=9)

        # Legenda
        patch_pos = mpatches.Patch(color=COLOR_BAR_POS, label='↑ Aumenta risco')
        patch_neg = mpatches.Patch(color=COLOR_BAR_NEG, label='↓ Reduz risco')
        ax.legend(
            handles=[patch_pos, patch_neg],
            loc='lower right',
            facecolor='#1A1A2E',
            edgecolor='#7F8C8D',
            labelcolor='#ECF0F1',
            fontsize=8,
        )

        # Rodapé com informação de versão
        fig.text(
            0.99, 0.01,
            'Maintenance Advisor — XAI Module (SHAP)',
            ha='right', va='bottom',
            color='#7F8C8D', fontsize=7, style='italic'
        )

        plt.tight_layout()

        # Serializar para Base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buffer.seek(0)

        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _get_top_feature(self, shap_values: list, feature_names: list) -> str:
        """Retorna o nome da feature com maior impacto SHAP absoluto."""
        if not shap_values:
            return 'N/A'
        np = _require_numpy()
        top_idx = int(np.argmax(np.abs(shap_values)))
        return feature_names[top_idx]

    def _generate_explanation_html(
        self,
        shap_values:         list,
        feature_names:       list,
        feature_values:      Dict[str, float],
        failure_probability: float,
        top_feature:         str,
    ) -> str:
        """
        Gera um bloco HTML com a explicação textual da predição em português.

        O texto é inserido automaticamente na descrição da Ordem de Manutenção.
        """
        risk_level_text = (
            '<strong style="color:#E74C3C;">CRÍTICO</strong>'
            if failure_probability >= 70 else (
                '<strong style="color:#F39C12;">MODERADO</strong>'
                if failure_probability >= 40 else
                '<strong style="color:#27AE60;">BAIXO</strong>'
            )
        )

        # Top 3 features por impacto
        sorted_features = sorted(
            zip(feature_names, shap_values, [feature_values.get(f, 0) for f in feature_names]),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:3]

        factors_html = ''
        for rank, (fname, shap_val, fval) in enumerate(sorted_features, 1):
            direction = '↑ contribui para falha' if shap_val >= 0 else '↓ reduz risco'
            color     = COLOR_BAR_POS if shap_val >= 0 else COLOR_BAR_NEG
            row_bg    = '#FFF5F5' if shap_val >= 0 else '#F5FFF5'
            factors_html += (
                f'<tr style="background: {row_bg};">'
                f'<td style="padding: 7px 12px; font-weight: bold; color: #2C3E50;">{rank}</td>'
                f'<td style="padding: 7px 12px; font-weight: bold;">{fname}</td>'
                f'<td style="padding: 7px 12px; font-family: monospace;">{fval:.2f}</td>'
                f'<td style="padding: 7px 12px; color: {color};">{direction}</td>'
                f'<td style="padding: 7px 12px; font-family: monospace; color: {color}; font-weight: bold;">{shap_val:+.4f}</td>'
                f'</tr>'
            )

        html = f"""
<div style="font-family: Arial, sans-serif; border-left: 4px solid #E74C3C; padding: 16px; background: #FDF9F9; width: 100%; box-sizing: border-box; border-radius: 4px;">
  <h3 style="color: #2C3E50; margin-top: 0; margin-bottom: 12px; font-size: 16px;">
    🤖 Análise Preditiva — Maintenance Advisor AI
  </h3>
  <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
    <tr>
      <td style="padding: 6px 12px 6px 0; width: 50%; vertical-align: top;">
        <strong>Probabilidade de Falha:</strong> {failure_probability:.1f}%
      </td>
      <td style="padding: 6px 0; width: 50%; vertical-align: top;">
        <strong>Nível de Risco:</strong> {risk_level_text}
      </td>
    </tr>
    <tr>
      <td colspan="2" style="padding: 6px 0;">
        <strong>Principal Fator Identificado:</strong> {top_feature}
      </td>
    </tr>
  </table>
  <h4 style="color: #2C3E50; margin-bottom: 8px; font-size: 14px;">📊 Top 3 Variáveis por Impacto (SHAP):</h4>
  <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
    <thead>
      <tr style="background: #2C3E50; color: #FFFFFF;">
        <th style="padding: 8px 12px; text-align: left; font-size: 13px;">#</th>
        <th style="padding: 8px 12px; text-align: left; font-size: 13px;">Variável</th>
        <th style="padding: 8px 12px; text-align: left; font-size: 13px;">Valor Atual</th>
        <th style="padding: 8px 12px; text-align: left; font-size: 13px;">Impacto</th>
        <th style="padding: 8px 12px; text-align: left; font-size: 13px;">SHAP</th>
      </tr>
    </thead>
    <tbody>{factors_html}</tbody>
  </table>
  <p style="color: #7F8C8D; font-size: 11px; border-top: 1px solid #EEE; padding-top: 8px; margin-bottom: 0;">
    <em>Análise gerada automaticamente pelo motor XAI (SHAP — SHapley Additive exPlanations).
    Os valores SHAP indicam a contribuição marginal de cada variável para o score de risco.</em>
  </p>
</div>
        """.strip()

        return html


# ==============================================================================
# 5. ROTEADOR DE MODELOS (AIRouter — agnóstico por categoria)
# ==============================================================================

class AIRouter:
    """
    Roteador central que direciona a telemetria para o engine de IA correto
    com base na categoria do equipamento.

    Mapeamento atual:
        'milling'    → MillingAIEngine   (XGBoost AI4I 2020)
        'compressor' → CompressorAIEngine (stub)
        'conveyor'   → ConveyorAIEngine   (stub)
        'lathe'      → MillingAIEngine    (reutiliza engine de fresagem)
        'generic'    → MillingAIEngine    (fallback)

    Como adicionar uma nova categoria:
        1. Crie uma classe herdando BaseAIEngine.
        2. Implemente o método `predict`.
        3. Adicione a entrada no dicionário `_ENGINE_MAP` abaixo.
    """

    _ENGINE_MAP = {
        'milling':    MillingAIEngine,
        'compressor': CompressorAIEngine,
        'conveyor':   ConveyorAIEngine,
        'lathe':      MillingAIEngine,     # Torno usa mesmas features por enquanto
        'generic':    MillingAIEngine,     # Fallback padrão
    }

    def __init__(self):
        # Cache de engines instanciadas (evita re-instanciar a cada predição)
        self._engine_cache: Dict[str, BaseAIEngine] = {}
        self._explainer = SHAPExplainer()

    def get_engine(self, ai_category: str) -> BaseAIEngine:
        """Retorna a instância do engine correto, usando cache."""
        category = ai_category or 'generic'
        if category not in self._engine_cache:
            engine_cls = self._ENGINE_MAP.get(category, MillingAIEngine)
            self._engine_cache[category] = engine_cls()
            _logger.info("Engine instanciado para categoria '%s': %s", category, engine_cls.__name__)
        return self._engine_cache[category]

    def run(
        self,
        ai_category:  str,
        features:     Dict[str, float],
        threshold:    float = 70.0,
        generate_xai: bool  = True,
    ) -> Dict[str, Any]:
        """
        Pipeline completo: predição → (opcional) explicação SHAP.

        Args:
            ai_category:  Categoria do equipamento (ex: 'milling').
            features:     Dicionário de features do sensor.
            threshold:    Limiar (%) acima do qual gera XAI e cria OS.
            generate_xai: Se False, pula a etapa SHAP (útil para predições em lote).

        Returns:
            dict com:
                - failure_probability (float)
                - is_critical         (bool)
                - model_version       (str)
                - shap_chart_b64      (str | None)
                - shap_explanation    (str | None)
                - top_feature         (str | None)
                - raw_prediction      (dict): resultado bruto do engine
        """
        engine = self.get_engine(ai_category)

        # ── Etapa 1: Predição ──────────────────────────────────────────
        try:
            raw_prediction = engine.predict(features)
        except Exception as e:
            _logger.error("Erro crítico no engine '%s': %s", ai_category, e, exc_info=True)
            raise RuntimeError(f"Falha no motor de IA para categoria '{ai_category}': {e}") from e

        failure_probability = raw_prediction.get('failure_probability', 0.0)
        is_critical         = failure_probability >= threshold
        shap_values         = raw_prediction.get('shap_values', [])

        _logger.info(
            "[AIRouter] Categoria: %s | Risco: %.2f%% | Crítico: %s | Features: %s",
            ai_category, failure_probability, is_critical,
            {k: f"{v:.2f}" for k, v in features.items()}
        )

        # ── Etapa 2: Explicabilidade SHAP (apenas se crítico) ───────────
        shap_chart_b64   = None
        shap_explanation = None
        top_feature      = None

        if is_critical and generate_xai and shap_values:
            try:
                feature_names = engine.FEATURE_NAMES or list(features.keys())
                shap_chart_b64, shap_explanation, top_feature = self._explainer.explain(
                    shap_values=shap_values,
                    feature_names=feature_names,
                    feature_values=raw_prediction.get('feature_values', features),
                    failure_probability=failure_probability,
                )
                _logger.info("[AIRouter] Gráfico SHAP gerado. Top feature: '%s'", top_feature)
            except Exception as e:
                _logger.error("Erro ao gerar explicação SHAP: %s", e, exc_info=True)
                # Não bloqueia o fluxo — predição continua sem XAI

        return {
            'failure_probability': failure_probability,
            'is_critical':         is_critical,
            'model_version':       raw_prediction.get('model_version', 'unknown'),
            'shap_chart_b64':      shap_chart_b64,
            'shap_explanation':    shap_explanation,
            'top_feature':         top_feature,
            'raw_prediction':      raw_prediction,
        }


# ==============================================================================
# 6. INSTÂNCIA GLOBAL DO ROUTER (Singleton simples)
# ==============================================================================

# Instância compartilhada para evitar re-instanciar engines a cada requisição.
# Uso: from maintenance_advisor.utils.ai_engine import ai_router_instance
ai_router_instance = AIRouter()


# ==============================================================================
# 7. TESTE RÁPIDO (executar diretamente: python ai_engine.py)
# ==============================================================================

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    print("=" * 60)
    print("  TESTE DO MOTOR DE IA — Maintenance Advisor")
    print("=" * 60)

    # Cenário 1: Leitura normal
    features_normal = {
        'Air temperature [K]':     298.5,
        'Process temperature [K]': 309.0,
        'Rotational speed [rpm]':  1550,
        'Torque [Nm]':             38.5,
        'Tool wear [min]':         45,
    }

    # Cenário 2: Leitura crítica
    features_critical = {
        'Air temperature [K]':     303.8,
        'Process temperature [K]': 313.2,
        'Rotational speed [rpm]':  1200,
        'Torque [Nm]':             68.9,
        'Tool wear [min]':         238,
    }

    router = AIRouter()

    for label, feats in [('NORMAL', features_normal), ('CRÍTICO', features_critical)]:
        print(f"\n[Cenário: {label}]")
        result = router.run(ai_category='milling', features=feats, threshold=70.0)
        print(f"  Risco:         {result['failure_probability']:.2f}%")
        print(f"  Crítico:       {result['is_critical']}")
        print(f"  Modelo:        {result['model_version']}")
        print(f"  Top Feature:   {result.get('top_feature', 'N/A')}")
        print(f"  SHAP Chart:    {'Gerado ✓' if result.get('shap_chart_b64') else 'Não gerado (abaixo do limiar)'}")

    print("\n✅ Teste concluído com sucesso.")
