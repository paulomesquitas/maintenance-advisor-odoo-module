# Maintenance Advisor — Predictive AI

> Módulo de Manutenção Preditiva com Inteligência Artificial Explicável (XAI) para o ERP Odoo 19  
> Desenvolvido como TCC da Especialização em Inteligência Artificial Aplicada à Indústria 4.0 pela Universidade Federal de Roraima (UFRR).

![Odoo](https://img.shields.io/badge/Odoo-19.0-714B67?style=flat-square&logo=odoo)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python)
![XGBoost](https://img.shields.io/badge/XGBoost-2.x-FF6600?style=flat-square)
![SHAP](https://img.shields.io/badge/SHAP-XAI-E74C3C?style=flat-square)
![Dataset](https://img.shields.io/badge/Dataset-AI4I%202020-27AE60?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

---

## Sobre o Projeto

O **Maintenance Advisor** é um módulo customizado para o **Odoo 19** que implementa **Manutenção Preditiva** com **Inteligência Artificial Explicável (XAI)** diretamente na interface nativa do sistema ERP.

O módulo analisa continuamente os dados dos sensores de equipamentos industriais e calcula, em tempo real, a **probabilidade de falha** de cada máquina — permitindo intervenções precisas antes que a falha ocorra. Diferente de soluções de "caixa-preta", o sistema utiliza **SHAP (SHapley Additive Explanations)** para explicar **por que** um equipamento foi classificado como crítico, identificando o sensor mais impactante em cada predição.

### Contexto Acadêmico

Este projeto foi desenvolvido como **Trabalho de Conclusão de Curso (TCC)** com o objetivo de:

1. Demonstrar a viabilidade de integrar modelos de Machine Learning em sistemas ERP open-source
2. Aplicar técnicas de XAI (Explicabilidade) em contexto industrial real
3. Comparar empiricamente algoritmos de predição (XGBoost vs Random Forest) e métodos de explicabilidade (SHAP vs LIME) usando o dataset AI4I 2020
4. Justificar com dados a escolha da stack XGBoost + SHAP para manutenção preditiva industrial

---

## Funcionalidades

### 🔮 Motor de Predição
- Modelo **XGBoost** treinado no **AI4I 2020 Predictive Maintenance Dataset** (UCI)
- Probabilidade de falha calculada em tempo real para cada leitura de telemetria
- Três níveis de risco: **Normal** (< 40%), **Moderado** (40–69%), **Crítico** (≥ 70%)
- Limiar de risco configurável por equipamento ou globalmente

### 🔍 Explicabilidade (XAI)
- **SHAP TreeExplainer** nativo para XGBoost — determinístico e eficiente
- Gráfico de barras SHAP gerado automaticamente para predições críticas
- Identificação automática da **variável mais crítica** (sensor principal)
- Análise textual explicando os fatores de risco em linguagem acessível

### 📊 Dashboard Preditivo
- Visão consolidada de todos os equipamentos monitorados
- KPIs em tempo real: total monitorado, críticos, moderados, normais
- Cards visuais com barra de risco e indicador colorido por nível
- Filtros por status e busca por nome

### 🚨 Alertas e Ordens de Manutenção
- **Banner de alerta vermelho** na ficha do equipamento quando crítico
- **Ordem de Manutenção criada automaticamente** ao atingir o limiar crítico
- OS preditiva inclui: probabilidade, fator principal, gráfico SHAP e análise textual
- Prioridade da OS calculada automaticamente com base no nível de risco

### 📡 Coleta de Telemetria
- Inserção manual de leituras via interface Odoo
- Simulação automática via **CRON jobs** (cenários: Normal, Degradado, Crítico)
- Histórico completo de leituras por equipamento

### ⚙️ Configuração
- Categorias de IA por tipo de equipamento (Fresadora/CNC, Torno, Genérico)
- Temperaturas inseridas em **°C** — conversão para Kelvin automática antes da predição
- Parâmetros de sistema via interface Odoo (sem edição de código)
- Smart buttons de contadores (Telemetria, OS Preditivas, Manutenção)

---

## Arquitetura

```
maintenance_advisor/
├── models/
│   ├── equipment.py          # Extensão de maintenance.equipment
│   ├── telemetry.py          # Modelo maintenance.telemetry
│   ├── ai_router.py          # Orquestrador do pipeline de IA
│   └── prediction_wizard.py  # Wizard de resultado da predição
├── utils/
│   └── ai_engine.py          # Motor de IA: XGBoost + SHAP
├── controllers/
│   └── main.py               # API REST para telemetria externa
├── views/
│   ├── equipment_views.xml        # Form + list view de equipamentos
│   ├── telemetry_views.xml        # Form + list + search de telemetria
│   ├── menu_views.xml             # Menu raiz independente
│   └── prediction_wizard_views.xml # Dialog de resultado
├── data/
│   └── cron_jobs.xml         # Ações agendadas (CRON)
├── security/
│   └── ir.model.access.csv   # Regras de acesso
└── static/
    ├── models/
    │   ├── milling_xgboost.joblib        # Modelo treinado
    │   └── milling_xgboost_metadata.json # Metadados do modelo
    └── src/js/
        └── predictive_dashboard.js       # Dashboard client-side
```

### Pipeline de IA

```
Telemetria (°C) → Conversão K → _validate_features()
                                        ↓
                              XGBoost.predict_proba()
                                        ↓
                            SHAP.TreeExplainer.shap_values()
                                        ↓
                         Atualiza equipment + Gera OS (se crítico)
```

---

## Embasamento Científico — Comparativo XGBoost vs Random Forest e SHAP vs LIME

### Por que XGBoost?

O AI4I 2020 é um dataset **altamente desbalanceado** (~3,4% de falhas). Os experimentos com validação cruzada estratificada 5-fold demonstraram:

| Métrica | XGBoost | Random Forest | Vencedor |
|---|---|---|---|
| **ROC-AUC** | 0.9795 | 0.9817 | RF (+0.002) |
| **PR-AUC** ⭐ | **0.9737** | **0.9632** | **XGBoost (+0.010)** |
| **F1-Score** | 0.7743 | 0.7804 | RF (+0.006) |
| **Recall** | 0.6780 | 0.9155 | RF (+0.237) |
| **Precisão** | 0.7149 | 0.6531 | XGBoost (+0.062) |
| **Tempo treino** | **3.8s** | 12.1s | **XGBoost (3x mais rápido)** |

> **PR-AUC** é a métrica mais relevante em datasets desbalanceados — o XGBoost vence na métrica que importa.

> O alto Recall do Random Forest indica comportamento "agressivo" (muitos falsos alarmes). Em ambiente industrial, 35% de alarmes falsos geram fadiga operacional.

### Por que SHAP?

| Critério | SHAP | LIME |
|---|---|---|
| Determinístico | ✅ Sempre o mesmo resultado | ❌ Varia entre execuções |
| Fidelidade ao modelo | ✅ Correlação > 0.95 com impacto real | ⚠️ Aproximação local |
| Velocidade | ✅ < 5ms por amostra | ❌ > 200ms por amostra |
| Análise global | ✅ Suportada | ❌ Apenas local |
| Nativo para árvores | ✅ TreeExplainer | ❌ Agnóstico (mais lento) |

### Por que não usar Acurácia?

Um modelo que **nunca prevê falha** atingiria **96,6% de acurácia** no AI4I 2020 — pois 96,6% das amostras são normais. Esse modelo seria completamente inútil em produção mas pareceria excelente pela acurácia. Por isso as métricas utilizadas são PR-AUC, F1-Score e Recall.

---

## Instalação

### Pré-requisitos

- Odoo 19.0
- Python 3.10+

### 1. Dependências Python

**Windows:**
```cmd
C:\Odoo19\python\python.exe -m pip install numpy pandas matplotlib scikit-learn xgboost shap joblib
```

**Linux/Ubuntu:**
```bash
sudo pip3 install numpy pandas matplotlib scikit-learn xgboost shap joblib --break-system-packages
```

**Verificação:**
```bash
python3 -c "import numpy, pandas, matplotlib, sklearn, xgboost, shap, joblib; print('OK')"
```

### 2. Instalar o Módulo

Copie a pasta `maintenance_advisor` para o diretório de addons do Odoo e execute:

```bash
# Linux
python3 odoo-bin -d seu_banco -i maintenance_advisor --stop-after-init

# Windows
D:\Odoo19\python\python.exe D:\Odoo19\server\odoo-bin -d odoo19 -i maintenance_advisor --stop-after-init
```

### 3. Ativar o Modelo de IA Real

Após treinar o modelo (veja seção Dataset e Treinamento), copie os arquivos:

```
maintenance_advisor/static/models/milling_xgboost.joblib
maintenance_advisor/static/models/milling_xgboost_metadata.json
```

E ative em `utils/ai_engine.py`:

```python
MOCK_MODE = False
```

---

## Dataset e Treinamento

### AI4I 2020 Predictive Maintenance Dataset

- **Fonte:** [UCI Machine Learning Repository](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset)
- **Amostras:** 10.000
- **Falhas:** ~339 (3,39%) — dataset desbalanceado
- **Features:** Temperatura do Ar [K], Temperatura do Processo [K], Velocidade Rotacional [rpm], Torque [Nm], Desgaste da Ferramenta [min]

### Treinar o Modelo

Use o notebook Jupyter disponível em `/notebooks/TCC_Comparativo_XGBoost_RF_SHAP_LIME.ipynb` no Google Colab:

1. Abra o notebook no Colab
2. Execute todas as células em ordem
3. A Seção 8 treina o modelo final e exporta os arquivos automaticamente
4. Copie os arquivos gerados para `static/models/`

---

## Categorias de Equipamentos

| Categoria | Tipo | Modelo de IA | Status |
|---|---|---|---|
| `milling` | Fresadora / CNC | XGBoost AI4I v1.1 | ✅ Ativo |
| `lathe` | Torno Mecânico | XGBoost AI4I v1.1 | ✅ Ativo (reutiliza milling) |
| `generic` | Genérico | XGBoost AI4I v1.1 | ✅ Ativo (fallback) |
| `compressor` | Compressor | — | 🔧 Trabalhos Futuros |
| `conveyor` | Esteira | — | 🔧 Trabalhos Futuros |

---

## Valores de Referência dos Sensores

| Sensor | Faixa Normal | Atenção | Crítico |
|---|---|---|---|
| Temperatura do Ar | 21–31 °C | > 29 °C | > 31 °C |
| Temperatura do Processo | 33–41 °C | > 39 °C | > 40 °C |
| Velocidade Rotacional | 1168–2886 rpm | < 1400 rpm ou > 2886 rpm | < 1250 rpm |
| Torque | 3.8–76.6 Nm | > 55 Nm | > 65 Nm |
| Desgaste da Ferramenta | 0–253 min | > 150 min | > 200 min |

---

## Tecnologias Utilizadas

| Camada | Tecnologia |
|---|---|
| ERP | Odoo 19.0 (Python/OWL) |
| Modelo Preditivo | XGBoost 2.x |
| Explicabilidade | SHAP (TreeExplainer) |
| Processamento | NumPy, Pandas |
| Visualização | Matplotlib |
| Serialização | Joblib |
| Dataset | AI4I 2020 (UCI Repository) |
| Comparativo | Scikit-learn, LIME |
| Notebook | Google Colab / Jupyter |

---

## Estrutura do Repositório

```
.
├── maintenance_advisor/          # Módulo Odoo
│   └── ...
├── notebooks/
│   └── TCC_Comparativo_XGBoost_RF_SHAP_LIME.ipynb  # Notebook de análise
├── docs/
│   └── Manual_Maintenance_Advisor.docx              # Manual do operador
└── README.md
```

---

## Licença

Este projeto está licenciado sob a **MIT License** — veja o arquivo [LICENSE](LICENSE) para detalhes.

---

## Autor

Paulo Roberto de Souza Mesquita Junior
paulo.adm@gmail.com

---

*Maintenance Advisor — Transformando dados de sensores em decisões de manutenção inteligentes.*
