#!/usr/bin/env python3
"""
GLPI Intelligent Agent v7.2 - Formatação Robusta e Prompt com Exemplo

Versão final que refina o prompt com um exemplo explícito e torna o código
de renderização de HTML mais robusto a variações na resposta da IA.
"""
import os
import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

from dataclasses import dataclass
import requests
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler

load_dotenv()

# =============================================================================
# MODELS DE DADOS
# =============================================================================
@dataclass
class GLPIConfig:
    url: str; app_token: str; user_token: str

@dataclass
class LLMConfig:
    api_url: str; model: str; analysis_prompt: str

@dataclass
class TicketDetails:
    id: str; title: str; content: str

@dataclass
class Solution:
    descricao_passos: str
    fonte_chamado: str

@dataclass
class LLMAgentResponse:
    sintese_problema: str
    hipotese_causa_raiz: str
    plano_de_acao: List[str]
    solucao_recomendada: Solution

def setup_logging(log_level: str = 'INFO') -> None:
    logging.basicConfig(level=getattr(logging, log_level.upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(), logging.FileHandler('glpi_agent_final.log')])

# =============================================================================
# SERVIÇO DO GLPI
# =============================================================================
class GLPIService:
    def __init__(self, config: GLPIConfig):
        self.config = config; self.session_token: Optional[str] = None; self.logger = logging.getLogger(__name__)
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        self.init_session()

    def init_session(self) -> bool:
        try:
            headers = {"App-Token": self.config.app_token, "Content-Type": "application/json"}
            payload = {"user_token": self.config.user_token}
            response = requests.post(f"{self.config.url}/initSession", headers=headers, json=payload, verify=False, timeout=10)
            response.raise_for_status()
            self.session_token = response.json().get("session_token")
            if self.session_token: self.logger.info("Sessão GLPI inicializada com sucesso."); return True
            self.logger.error(f"Falha ao obter session_token do GLPI. Resposta: {response.text}"); return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erro de conexão ao inicializar sessão: {e}"); self.session_token = None; return False

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        if not self.session_token and not self.init_session(): return None
        headers = {"App-Token": self.config.app_token, "Session-Token": self.session_token, "Content-Type": "application/json"}
        try:
            response = requests.request(method, f"{self.config.url}/{endpoint}", headers=headers, verify=False, timeout=20, **kwargs)
            if response.status_code == 401:
                self.logger.warning("Sessão GLPI expirada. Reinicializando...");
                if self.init_session():
                    headers["Session-Token"] = self.session_token
                    response = requests.request(method, f"{self.config.url}/{endpoint}", headers=headers, verify=False, timeout=20, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erro na requisição API para {method} {endpoint}: {e}"); return None

    def get_all_active_tickets_from_api(self, active_status_ids: List[int]) -> List[Dict]:
        self.logger.info("Buscando chamados mais recentes para filtragem (Estratégia Validada)...")
        payload = {"is_deleted": 0, "forcedisplay": [2, 1, 24, 12], "range": "0-1000", "sort": 15, "order": "DESC"}
        response_data = self._make_request("POST", "search/Ticket", json=payload)
        full_ticket_list = []
        if isinstance(response_data, dict) and 'data' in response_data: full_ticket_list = response_data['data']
        elif isinstance(response_data, list): full_ticket_list = response_data
        if not full_ticket_list: self.logger.info("Nenhum chamado foi retornado pela API."); return []
        self.logger.info(f"API retornou {len(full_ticket_list)} chamados. Filtrando localmente por status...")
        active_tickets_data = [item for item in full_ticket_list if item.get('12') in active_status_ids]
        self.logger.info(f"Encontrados {len(active_tickets_data)} chamados com status ativos."); return active_tickets_data

    def search_solved_tickets(self, ticket_title: str, ticket_content: Optional[str]) -> List[Dict]:
        if not ticket_content: ticket_content = ""
        keywords = " ".join(ticket_content.split()[:20])
        search_text = f"{ticket_title} {keywords}"
        self.logger.info(f"Buscando chamados similares com o texto: '{search_text[:100]}...'")

        criteria = [{'field': 12, 'searchtype': 'equals', 'value': [5, 6]}]
        payload = {"is_deleted": 0, "criteria": criteria, "searchText": search_text, "forcedisplay": [2, 1, 71], "range": "0-5"}
        results = self._make_request("POST", "search/Ticket", json=payload)
        return [{"id": r.get('2'), "title": r.get('1'), "solution": r.get('71')} for r in results] if results and isinstance(results, list) else []

    def search_knowledge_base(self, query: str) -> List[Dict]:
        payload = {"searchText": query, "forcedisplay": [1, 2], "range": "0-5"}
        results = self._make_request("POST", "search/KnowbaseItem", json=payload)
        return [{"id": r.get('id'), "name": r.get('1'), "answer": r.get('2')} for r in results] if results and isinstance(results, list) else []

    def add_followup(self, ticket_id: str, content: str) -> bool:
        payload = {"input": {"tickets_id": int(ticket_id), "content": content, "is_private": 1}}
        response = self._make_request("POST", "TicketFollowup", json=payload)
        if response:
            self.logger.info(f"Acompanhamento adicionado com sucesso ao chamado #{ticket_id}.")
            return True
        self.logger.error(f"Falha ao adicionar acompanhamento ao chamado #{ticket_id}. A API rejeitou o payload.")
        return False

# =============================================================================
# SERVIÇO DO LLM
# =============================================================================
class LLMService:
    def __init__(self, config: LLMConfig): self.config = config; self.logger = logging.getLogger(__name__)
    def generate_guidance(self, ticket_data: Dict, user_history: List[Dict], global_solutions: List[Dict], kb_articles: List[Dict]) -> Optional[LLMAgentResponse]:
        self.logger.info(f"Gerando análise sênior para o chamado #{ticket_data.get('2')}...");
        ticket = TicketDetails(id=str(ticket_data.get('2')), title=ticket_data.get('1'), content=ticket_data.get('24'))
        prompt = f"""{self.config.analysis_prompt} **## Chamado Atual ##** ID:{ticket.id}, Título:{ticket.title}, Descrição:{ticket.content} **## Contexto de Pesquisa ##** **Soluções Globais:** {json.dumps(global_solutions, indent=2, ensure_ascii=False)} **Base de Conhecimento:** {json.dumps(kb_articles, indent=2, ensure_ascii=False)} **## Resposta JSON ##**""";
        try:
            payload = {"model": self.config.model, "prompt": prompt, "stream": False, "format": "json"};
            response = requests.post(f"{self.config.api_url.strip()}/api/generate", json=payload, timeout=120);
            response.raise_for_status();
            response_json = json.loads(response.json().get("response", "{}").strip());

            solucao = response_json.get('solucao_recomendada', {})
            return LLMAgentResponse(
                sintese_problema=response_json.get("sintese_problema", "Não foi possível sintetizar o problema."),
                hipotese_causa_raiz=response_json.get("hipotese_causa_raiz", "Nenhuma hipótese clara pôde ser formada."),
                plano_de_acao=response_json.get("plano_de_acao", []),
                solucao_recomendada=Solution(
                    descricao_passos=solucao.get("descricao_passos", "Nenhuma solução específica encontrada nos dados."),
                    fonte_chamado=solucao.get("fonte_chamado", "N/A")
                )
            )
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.logger.error(f"Falha ao gerar relatório para o chamado #{ticket.id}. Erro: {e}"); return None

# =============================================================================
# APLICAÇÃO PRINCIPAL
# =============================================================================
def build_html_list(items: List[Any], item_type: str = 'disc') -> str:
    """Função auxiliar para construir listas HTML de forma robusta."""
    if not items or not isinstance(items, list):
        return "<li>Nenhuma sugestão fornecida.</li>"

    html_items = ""
    for item in items:
        # Garante que o item é uma string antes de adicioná-lo
        html_items += f"<li style='margin-bottom: 8px;'>{str(item)}</li>"

    return html_items

class TicketAgentApp:
    def __init__(self):
        log_level = os.getenv('LOG_LEVEL', 'INFO');
        self.assessment_interval_minutes = int(os.getenv('ASSESSMENT_INTERVAL_MINUTES', '30'));
        setup_logging(log_level);
        self.logger = logging.getLogger(__name__);
        glpi_config = GLPIConfig(url=os.getenv('GLPI_URL'), app_token=os.getenv('GLPI_APP_TOKEN'), user_token=os.getenv('GLPI_USER_TOKEN'));
        llm_config = LLMConfig(api_url=os.getenv('OLLAMA_API_URL'), model=os.getenv('OLLAMA_MODEL'), analysis_prompt=os.getenv('OLLAMA_PROMPT_BASE_N1'));
        status_ids_str = os.getenv('GLPI_ACTIVE_STATUS_IDS', '1,2,3,4');
        self.active_status_ids = [int(sid.strip()) for sid in status_ids_str.split(',')];
        if not all(vars(glpi_config).values()) or not all(vars(llm_config).values()):
            raise ValueError("Erro Crítico: Verifique se TODAS as variáveis de ambiente estão definidas no .env")
        self.glpi_service = GLPIService(glpi_config);
        self.llm_service = LLMService(llm_config);
        self.processed_ids_path = "/tmp/glpi_agent_processed_ids.txt";
        self.logger.info(f"Agente Inteligente inicializado. Rastreando em: {self.processed_ids_path}")

    def _load_processed_ids(self) -> Set[str]:
        if not os.path.exists(self.processed_ids_path): return set()
        try:
            with open(self.processed_ids_path, 'r') as f: return {line.strip() for line in f if line.strip()}
        except IOError as e: self.logger.error(f"Não foi possível ler o arquivo de IDs: {e}"); return set()
    def _mark_as_processed(self, ticket_id: str) -> None:
        try:
            with open(self.processed_ids_path, 'a') as f: f.write(f"{ticket_id}\n")
            self.logger.info(f"Chamado #{ticket_id} marcado como processado.")
        except IOError as e: self.logger.error(f"Não foi possível escrever no arquivo de IDs: {e}")

    def run_agent_cycle(self):
        self.logger.info("====== INICIANDO CICLO DE ANÁLISE DE CHAMADOS ======")
        try:
            processed_ids = self._load_processed_ids()
            active_tickets = self.glpi_service.get_all_active_tickets_from_api(self.active_status_ids)
            tickets_to_process = [ticket for ticket in active_tickets if str(ticket.get('2')) not in processed_ids]

            if not tickets_to_process: self.logger.info("Nenhum chamado novo para processar encontrado neste ciclo."); return

            self.logger.info(f"Encontrados {len(tickets_to_process)} chamados para processar.")
            for ticket_data in tickets_to_process:
                ticket_id = str(ticket_data.get('2'))
                ticket_title = ticket_data.get('1', 'N/A')
                ticket_content = ticket_data.get('24', '')
                self.logger.info(f"--- Processando chamado #{ticket_id}: '{ticket_title}' ---");

                global_solutions = self.glpi_service.search_solved_tickets(ticket_title, ticket_content)
                kb_articles = self.glpi_service.search_knowledge_base(ticket_title)

                guidance = self.llm_service.generate_guidance(ticket_data, [], global_solutions, kb_articles);

                if guidance:
                    # Usa a nova função robusta para construir a lista HTML
                    plano_acao_html = build_html_list(guidance.plano_de_acao)

                    final_html = f"""
                    <div style="max-width: 700px; margin: auto; font-family: 'Segoe UI', Arial, sans-serif; background: #fdfdfd; border: 1px solid #cfd8dc; padding: 24px; border-radius: 8px; color: #263238; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);">
                        <div style="display: flex; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #eceff1; padding-bottom: 16px;">
                            <div style="font-size: 28px; margin-right: 15px;">🤖</div>
                            <h2 style="margin: 0; font-size: 20px; color: #37474f;">Análise (IA)</h2>
                        </div>
                        <h3 style="font-size: 16px; color: #37474f;">📄 Síntese do Problema</h3>
                        <p style="font-size: 15px; line-height: 1.6;">{guidance.sintese_problema}</p>
                        <h3 style="font-size: 16px; color: #37474f; margin-top: 24px;">💡 Hipótese de Causa Raiz</h3>
                        <p style="font-size: 15px; line-height: 1.6;">{guidance.hipotese_causa_raiz}</p>
                        <h3 style="font-size: 16px; color: #37474f; margin-top: 24px;">📋 Plano de Ação Tático</h3>
                        <ul style="font-size: 15px; line-height: 1.6; list-style-type: '☑️ '; padding-left: 20px;">{plano_acao_html}</ul>
                        <div style="margin-top: 28px; background-color: #eceff1; padding: 14px 18px; border-left: 4px solid #37474f; border-radius: 6px;">
                            <h3 style="margin-top: 0; font-size: 16px; color: #37474f;">⭐ Solução Recomendada (Baseado em Casos Anteriores)</h3>
                            <p style="font-size: 15px; line-height: 1.6; margin-bottom: 5px;"><strong>Passos:</strong> {guidance.solucao_recomendada.descricao_passos}</p>
                            <p style="font-size: 13px; color: #546e7a; margin-top: 5px;"><em><strong>Fonte:</strong> {guidance.solucao_recomendada.fonte_chamado}</em></p>
                        </div>
                    </div>
                    """

                    if self.glpi_service.add_followup(ticket_id, final_html):
                        self._mark_as_processed(ticket_id)
                else:
                    self.logger.warning(f"Não foi possível gerar relatório para o chamado #{ticket_id}.");
                time.sleep(5)
        except Exception as e:
            self.logger.critical(f"Erro inesperado no ciclo do agente: {e}", exc_info=True)
        finally:
            self.logger.info("====== CICLO DE ANÁLISE CONCLUÍDO ======")

if __name__ == "__main__":
    try:
        app = TicketAgentApp()
        scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
        scheduler.add_job(app.run_agent_cycle, 'interval', minutes=app.assessment_interval_minutes, next_run_time=datetime.now())
        logging.info(f"Agente agendado para rodar a cada {app.assessment_interval_minutes} minutos. Pressione Ctrl+C para sair.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Serviço do Agente encerrado.")
    except ValueError as e:
        logging.critical(e)
