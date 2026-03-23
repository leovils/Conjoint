import streamlit as st
import pandas as pd
import numpy as np
import io
import json
import os
import requests
import uuid
from datetime import datetime

from conjoint_engine import ConjointEngine

# Configuração da página
st.set_page_config(page_title="Pesquisa - Conjoint Analysis", layout="wide")

CONFIG_FILE = "survey_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

if "config" not in st.session_state:
    st.session_state.config = load_config()

respondent_mode = st.session_state.config is not None

# Init session variables
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "profiling_completed" not in st.session_state:
    st.session_state.profiling_completed = False

if "profile_answers" not in st.session_state:
    st.session_state.profile_answers = {}

if "engine" not in st.session_state:
    if respondent_mode:
        cfg = st.session_state.config
        st.session_state.engine = ConjointEngine(cfg["attributes"], cfg["forbidden"])
        st.session_state.intro_text = cfg.get("intro_text", "")
        st.session_state.webhook_url = cfg.get("webhook_url", "")
        if not cfg.get("profile_questions"):
            st.session_state.profiling_completed = True
    else:
        st.session_state.engine = None
        st.session_state.intro_text = "Bem-vindo à pesquisa! Por favor, escolha a opção que mais prefere."
        st.session_state.webhook_url = ""
        st.session_state.attributes = {}
        st.session_state.forbidden = []

if "setup_done" not in st.session_state:
    st.session_state.setup_done = respondent_mode

if "current_pair" not in st.session_state:
    if st.session_state.setup_done and respondent_mode:
        st.session_state.current_pair = st.session_state.engine.generate_pair()
    else:
        st.session_state.current_pair = None

if "survey_finished" not in st.session_state:
    st.session_state.survey_finished = False

import threading

def _bg_post(url, payload):
    try:
        requests.post(url, json=payload, timeout=15)
    except:
        pass

def send_to_webhook(pair, chosen):
    webhook = st.session_state.webhook_url
    if not webhook: return
    
    payload = {
        "user_id": st.session_state.user_id,
        "timestamp": datetime.now().isoformat(),
        "round": len(st.session_state.engine.history),
        "choice": chosen
    }
    
    for k, v in pair['A'].items(): payload[f"OpA_{k}"] = v
    for k, v in pair['B'].items(): payload[f"OpB_{k}"] = v
        
    for q, a in st.session_state.profile_answers.items():
        payload[f"Perfil_{q}"] = a
        
    # Envia em segundo plano (background) para não travar a tela
    threading.Thread(target=_bg_post, args=(webhook, payload), daemon=True).start()
    st.session_state.webhook_error = None

st.title("Conjoint Analysis - Pesquisa Interativa")

def render_profile_form():
    st.write(st.session_state.intro_text)
    cfg = st.session_state.config
    questions = cfg.get("profile_questions", [])
    
    st.subheader("Sobre você")
    with st.form("profiling_form"):
        answers = {}
        for idx, q in enumerate(questions):
            answers[q["question"]] = st.selectbox(f"**{q['question']}**", q["options"], key=f"ans_{idx}")
            
        submit = st.form_submit_button("Continuar para a Pesquisa")
        if submit:
            st.session_state.profile_answers = answers
            st.session_state.profiling_completed = True
            st.rerun()

def render_survey():
    if not st.session_state.setup_done:
        st.info("Por favor, conclua a configuração (aba 1).")
        return
        
    if st.session_state.survey_finished:
        st.success("A pesquisa foi concluída! Suas respostas foram computadas com sucesso. Muito obrigado por participar!")
        return
        
    if st.session_state.get("webhook_error"):
        st.error("Erro da Rodada Anterior: " + st.session_state.webhook_error)
        
    cfg = st.session_state.config or {}
    if not cfg.get("profile_questions"):
        st.write(st.session_state.intro_text)
    else:
        st.write("Avalie as opções e escolha a que você mais prefere em cada par:")
    
    history_len = len(st.session_state.engine.history)
    st.progress(min(history_len / 18.0, 1.0))
    st.caption(f"Rodada: {history_len + 1} (Mínimo: 10 pares)")
    
    pair = st.session_state.current_pair
    
    if pair:
        colA, colB = st.columns(2)
        with colA:
            st.subheader("Opção A")
            for k, v in pair['A'].items():
                st.write(f"**{k}:** {v}")
            if st.button("Escolher Opção A ✅", use_container_width=True):
                st.session_state.survey_finished = st.session_state.engine.register_choice(pair, 'A')
                send_to_webhook(pair, 'A')
                st.session_state.current_pair = st.session_state.engine.generate_pair()
                st.rerun()

        with colB:
            st.subheader("Opção B")
            for k, v in pair['B'].items():
                st.write(f"**{k}:** {v}")
            if st.button("Escolher Opção B ✅", use_container_width=True):
                st.session_state.survey_finished = st.session_state.engine.register_choice(pair, 'B')
                send_to_webhook(pair, 'B')
                st.session_state.current_pair = st.session_state.engine.generate_pair()
                st.rerun()

if respondent_mode:
    if not st.session_state.profiling_completed:
        render_profile_form()
    else:
        render_survey()
        
    if st.sidebar.checkbox("Acesso Administrativo"):
        st.sidebar.warning("Para voltar à tela de configuração, apague/delete o arquivo 'survey_config.json' da sua pasta.")
else:
    tab_config, tab_survey, tab_report = st.tabs(["1. Configuração e Nuvem", "2. Visualizar/Coletar", "3. Relatórios Experimentais"])
    
    with tab_config:
        st.header("1. Textos e Integração")
        st.session_state.intro_text = st.text_area("Texto de Convite da Pesquisa", value=st.session_state.intro_text)
        st.session_state.webhook_url = st.text_input("Webhook URL (Link do Google Apps Script para salvar na Nuvem)", value=st.session_state.webhook_url)
        
        st.markdown("---")
        st.header("2. Perguntas de Perfil do Respondente (Opcional)")
        st.write("Adicione perguntas extras para ir para o banco de dados (ex: idade, gênero, cidade).")
        num_profile = st.number_input("Número de perguntas", min_value=0, max_value=10, value=0)
        profile_config = []
        if num_profile > 0:
            for i in range(num_profile):
                st.markdown(f"**Pergunta {i+1}**")
                colQ, colO = st.columns(2)
                with colQ:
                    q_text = st.text_input(f"Texto da Pergunta", key=f"pq_{i}", value=f"Sua Pergunta {i+1}?")
                with colO:
                    q_opts = st.text_input(f"Opções (separadas por vírgula, de 3 a 5 opções)", key=f"po_{i}", value="Opção 1,Opção 2,Opção 3")
                if q_text:
                    profile_config.append({
                        "question": q_text, 
                        "options": [opt.strip() for opt in q_opts.split(",") if opt.strip()]
                    })
        
        st.markdown("---")
        st.header("3. Atributos da Pesquisa Conjunta")
        st.write("Exatamente 5 atributos com 3 níveis para manter a integridade da Análise Estatística.")
        
        attr_inputs = {}
        colA1, colA2 = st.columns(2)
        cols = [colA1, colA2, colA1, colA2, colA1]
        
        for i in range(1, 6):
            with cols[i-1]:
                attr_name = st.text_input(f"Nome do Atributo {i}", value=f"Atributo {i}", key=f"attr_name_{i}")
                levels_str = st.text_input(f"Níveis (separados por virgula)", value=f"Nível 1,Nível 2,Nível 3", key=f"lvl_{i}")
                attr_inputs[attr_name] = [l.strip() for l in levels_str.split(",") if l.strip()]

        st.markdown("---")
        st.header("4. Combinações Proibidas")
        st.write("Remova perfis ilógicos que nunca deveriam ser comparados (ex: Alta Qualidade + Preço Extremo Baixo).")
        all_levels = []
        for k, v in attr_inputs.items():
            for lvl in v:
                all_levels.append(f"{k}: {lvl}")
                
        forbidden_pairs = st.multiselect("Pares proibidos", options=[f"{a} + {b}" for i, a in enumerate(all_levels) for b in all_levels[i+1:]])

        st.markdown("---")
        colSave1, colSave2 = st.columns(2)
        with colSave1:
            if st.button("Aplicar Configurações e Testar Visão"):
                st.session_state.attributes = attr_inputs
                st.session_state.forbidden = forbidden_pairs
                st.session_state.engine = ConjointEngine(attr_inputs, forbidden_pairs)
                st.session_state.setup_done = True
                
                # Mock config object temporarily for the test
                st.session_state.config = {
                    "intro_text": st.session_state.intro_text,
                    "profile_questions": profile_config,
                    "attributes": attr_inputs,
                    "forbidden": forbidden_pairs
                }
                
                if not profile_config: 
                    st.session_state.profiling_completed = True
                else: 
                    st.session_state.profiling_completed = False
                    
                st.session_state.profile_answers = {}
                st.session_state.current_pair = st.session_state.engine.generate_pair()
                st.session_state.survey_finished = False
                st.success("Salvo para teste. Vá até a aba '2. Visualizar/Coletar' para ver o fluxo.")
        
        with colSave2:
            if st.button("Travar Configuração & Preparar para Nuvem"):
                valid = True
                for k, v in attr_inputs.items():
                    if len(v) != 3:
                        st.error(f"O atributo '{k}' precisa ter exatamente 3 níveis.")
                        valid = False
                
                if valid and len(attr_inputs) == 5:
                    config_data = {
                        "intro_text": st.session_state.intro_text,
                        "webhook_url": st.session_state.webhook_url,
                        "profile_questions": profile_config,
                        "attributes": attr_inputs,
                        "forbidden": forbidden_pairs
                    }
                    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=4)
                        
                    st.success("Pronto! Arquivo 'survey_config.json' exportado. Pise no F5/Atualize a página para entrar no Modo de Respondente final.")

    with tab_survey:
        if not st.session_state.profiling_completed and st.session_state.config and st.session_state.config.get("profile_questions"):
            render_profile_form()
        else:
            render_survey()
        
    with tab_report:
        st.header("Análise Consolidada da Nuvem (Google Sheets)")
        st.write("Baixe a sua planilha com todas as respostas no Google Sheets acessando **Arquivo > Fazer Download > Valores Separados por Vírgulas (.csv)** e arraste ela aqui.")
        
        uploaded_file = st.file_uploader("Upload do CSV consolidado", type=["csv"])
        
        if uploaded_file is not None:
            df_cloud = pd.read_csv(uploaded_file)
            st.subheader("Base Bruta Carregada")
            st.dataframe(df_cloud)
            
            if st.button("Calcular Resultados Estatísticos Totais"):
                if not st.session_state.setup_done:
                    st.error("Você precisa configurar seus atributos na Aba 1 antes (ou ter travado a configuração) para o motor matemático saber fazer o pareamento correto das respostas!")
                else:
                    engine_cloud = ConjointEngine(st.session_state.attributes, st.session_state.forbidden)
                    history_rebuilt = []
                    
                    try:
                        for _, row in df_cloud.iterrows():
                            raw_A = {}
                            raw_B = {}
                            for attr in st.session_state.attributes.keys():
                                colA = f"OpA_{attr}"
                                colB = f"OpB_{attr}"
                                if colA in row and colB in row:
                                    # Forçando string para parear exato com os níveis cadastrados
                                    raw_A[attr] = str(row[colA])
                                    raw_B[attr] = str(row[colB])
                                    
                            if raw_A and raw_B and "choice" in row:
                                choice = str(row["choice"]).strip()
                                diff = engine_cloud._encode_profile(raw_A) - engine_cloud._encode_profile(raw_B)
                                history_rebuilt.append({
                                    'raw_A': raw_A,
                                    'raw_B': raw_B,
                                    'diff_vector': diff,
                                    'choice_A': 1 if choice == 'A' else 0
                                })
                                
                        if len(history_rebuilt) < 5:
                            st.warning("O arquivo possui poucas rodadas registradas. O algoritmo pode ter resultados não confiáveis (Alta Variância).")
                            
                        # Sobrescrevendo a história do motor com a da Nuvem
                        engine_cloud.history = history_rebuilt
                        engine_cloud.betas = engine_cloud._calculate_betas()
                        
                        st.markdown("---")
                        st.subheader("🏆 Importância Relativa dos Atributos (%)")
                        st.write("Isso responde à pergunta: **O que os seus clientes mais valorizam na sua oferta?**")
                        st.bar_chart(engine_cloud.get_importance_df().set_index("Atributo"))
                        
                        st.subheader("📊 Part-Worth Utilities (Peso de cada Nível)")
                        st.write("Isso mostra o valor absoluto positivo (+) ou negativo (-) que cada nível de um atributo tem para formar a decisão.")
                        st.dataframe(engine_cloud.get_utilities_df())
                        
                    except Exception as e:
                        st.error(f"Erro ao processar as colunas do seu CSV: Verifique se ele corresponde fielmente aos atributos cadastrados. Erro detalhado: {str(e)}")
                        
        st.markdown("---")
        st.header("Teste Local (Apenas suas respostas)")
        if not st.session_state.setup_done:
            st.info("Teste sua pesquisa primeiro na Aba 2.")
        elif len(st.session_state.engine.history) == 0:
            st.info("Nenhuma escolha simulada localmente no momento.")
        else:
            engine = st.session_state.engine
            df_history = engine.get_history_df()
            
            if st.session_state.profile_answers:
                for k, v in st.session_state.profile_answers.items():
                    df_history[f"Perfil_{k}"] = v
            
            st.dataframe(df_history)
            
            if hasattr(engine, 'betas') and engine.betas is not None:
                st.subheader("Cálculos Experimentais Locais")
                st.dataframe(engine.get_utilities_df())
                st.bar_chart(engine.get_importance_df().set_index("Atributo"))
