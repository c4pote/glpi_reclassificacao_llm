#!/usr/bin/env python3
"""
GLPI Ticket Assessor - Backend Service

Versão: 6.0.0 - Lógica de rastreamento de chamados via arquivo de texto local.
"""
import os
import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

import requests
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler

load_dotenv()

# =============================================================================
# CONFIGURATION AND DATA MODELS
# =============================================================================
from dataclasses import dataclass

# ! MODIFICADO - GLPIConfig não precisa mais do ID do campo personalizado
@dataclass
class GLPIConfig:
    url: str; app_token: str; user_token: str
    @classmethod
    def from_env(cls) -> 'GLPIConfig':
        return cls(url=os.getenv('GLPI_URL', ''), app_token=os.getenv('GLPI_APP_TOKEN', ''), user_token=os.getenv('GLPI_USER_TOKEN', ''))

# ... (outras classes de configuração e modelos de dados sem alterações) ...
@dataclass
class LLMConfig:
    api_urls: List[str]; model: str; analysis_prompt: str
    @classmethod
    def from_env(cls) -> 'LLMConfig':
        return cls(api_urls=os.getenv('OLLAMA_API_URLS', 'http://localhost:11434').split(','), model=os.getenv('OLLAMA_MODEL', 'llama3'), analysis_prompt=os.getenv('OLLAMA_ANALYSIS_PROMPT', ''))

@dataclass
class AppConfig:
    log_level: str; assessment_interval_minutes: int
    @classmethod
    def from_env(cls) -> 'AppConfig':
        return cls(log_level=os.getenv('LOG_LEVEL', 'INFO'), assessment_interval_minutes=int(os.getenv('ASSESSMENT_INTERVAL_MINUTES', '30')))

@dataclass
class Ticket:
    id: str; title: str; content: str

@dataclass
class LLMAnalysisResult:
    priority: int; urgency: int; new_title: str; new_category_id: int

def setup_logging(log_level: str = 'INFO') -> None:
    logging.basicConfig(level=getattr(logging, log_level.upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(), logging.FileHandler('glpi_assessor.log')])

# =============================================================================
# GLPI SERVICE
# =============================================================================
class GLPIService:
    def __init__(self, config: GLPIConfig):
        self.config = config; self.session_token: Optional[str] = None; self.logger = logging.getLogger(__name__); self.init_session()

    # ... (init_session e _make_request sem alterações) ...
    def init_session(self) -> bool:
        try:
            headers = {"App-Token": self.config.app_token, "Content-Type": "application/json"}; payload = {"user_token": self.config.user_token}
            response = requests.post(f"{self.config.url}/initSession", headers=headers, json=payload, verify=False, timeout=10)
            response.raise_for_status()
            self.session_token = response.json().get("session_token")
            if self.session_token: self.logger.info("Sessão GLPI inicializada com sucesso."); return True
            self.logger.error(f"Falha ao obter session_token do GLPI. Resposta: {response.text}"); return False
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400: self.logger.critical("ERRO 400 (Bad Request): Falha de Autenticação com o GLPI. Verifique os TOKENS no arquivo .env.")
            else: self.logger.error(f"Erro HTTP inesperado ao inicializar sessão GLPI: {e}")
            self.session_token = None; return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erro de conexão ao inicializar sessão GLPI: {e}"); self.session_token = None; return False

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        if not self.session_token and not self.init_session(): return None
        headers = {"App-Token": self.config.app_token, "Session-Token": self.session_token, "Content-Type": "application/json"}
        try:
            response = requests.request(method, f"{self.config.url}/{endpoint}", headers=headers, verify=False, timeout=20, **kwargs)
            if response.status_code == 401:
                self.logger.warning("Sessão GLPI expirada. Reinicializando...");
                if self.init_session(): headers["Session-Token"] = self.session_token; response = requests.request(method, f"{self.config.url}/{endpoint}", headers=headers, verify=False, timeout=20, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erro na requisição API para {method} {endpoint}: {e.response.status_code} {e.response.reason} - {e.response.text}")
            return None
        except requests.exceptions.RequestException as e: self.logger.error(f"Erro na requisição API para {method} {endpoint}: {e}"); return None

    # ! MODIFICADO - O nome e a lógica foram ajustados para buscar todos os chamados não solucionados.

# =============================================================================
# DENTRO DA CLASSE GLPIService - VERSÃO FINAL CORRIGIDA
# =============================================================================



    def get_all_active_tickets(self) -> List[Ticket]:
        """
        Busca os chamados mais recentes e filtra localmente para processar
        apenas os que estão ativos.
        """
        self.logger.info("Buscando os chamados mais recentes para filtragem...")

        # 1. Payload com a ordenação por data de criação (mais novos primeiro).
        payload = {
            "is_deleted": 0,
            "forcedisplay": [2, 1, 24, 12],  # ID, Título, Conteúdo, Status
            "range": "0-2000",
            # A MUDANÇA CRÍTICA: Ordenar por data de criação, do mais novo para o mais antigo
            "sort": 15,  # 15 é o ID do campo 'date_creation' (Data de Criação)
            "order": "DESC"
        }

        response_data = self._make_request("POST", "search/Ticket", json=payload)

        full_ticket_list = []
        if isinstance(response_data, dict) and 'data' in response_data:
            full_ticket_list = response_data['data']
        elif isinstance(response_data, list):
            full_ticket_list = response_data

        if not full_ticket_list:
            self.logger.info("Nenhum chamado foi retornado pela API.")
            return []

        self.logger.info(f"API retornou {len(full_ticket_list)} chamados recentes. Filtrando apenas os ativos...")

        # 2. Filtramos a lista comparando NÚMERO com NÚMERO.
        active_tickets_data = [
            item for item in full_ticket_list
            if item.get('12') in [1, 2, 3, 4]
        ]

        # 3. Montamos a lista final de objetos Ticket.
        tickets = [
            Ticket(id=str(item.get('2')), title=item.get('1', "N/A"), content=item.get('24', ""))
            for item in active_tickets_data
        ]

        self.logger.info(f"Encontrados {len(tickets)} chamados verdadeiramente ativos para processar.")
        return tickets

    def oldget_all_active_tickets(self) -> List[Ticket]:
        """Busca todos os chamados que não estão Solucionados ou Fechados."""
        self.logger.info("Buscando todos os chamados ativos (não solucionados/fechados) no GLPI...")

        # Critérios: Status NÃO é Solucionado (ID 5) E NÃO é Fechado (ID 6)
        #criteria = [
        #    {'field': 12, 'searchtype': 'notequals', 'value': 5, 'link': 'AND'},
        #    {'field': 12, 'searchtype': 'notequals', 'value': 6}
        #]

        criteria = [
            {
            'field': 12,  # ID do campo "Status"
            'searchtype': 'equals',
            'value': [1, 2, 3, 4]  # Uma lista de valores é o equivalente ao "IN" do SQL
            }
        ]

        payload = {"is_deleted": 0, "criteria": criteria, "forcedisplay": [2, 1, 24], "range": "0-2000"}

        response_data = self._make_request("POST", "search/Ticket", json=payload)
        print('COCO')
        print(response_data)
        ticket_list = []
        if isinstance(response_data, dict) and 'data' in response_data:
            ticket_list = response_data['data']
        elif isinstance(response_data, list):
            ticket_list = response_data

        tickets = [Ticket(id=str(item.get('2')), title=item.get('1', "N/A"), content=item.get('24', "")) for item in ticket_list]
        self.logger.info(f"Encontrados {len(tickets)} chamados ativos.")
        return tickets

    # ! MODIFICADO - Apenas atualiza o chamado, não o marca mais.
    def update_ticket(self, ticket_id: str, analysis: LLMAnalysisResult) -> bool:
        """Atualiza um chamado com os dados da análise da LLM."""
        self.logger.info(f"Preparando atualização para chamado #{ticket_id}...")

        payload_input = {"name": analysis.new_title, "priority": analysis.priority, "urgency": analysis.urgency}
        if analysis.new_category_id > 0:
            payload_input["itilcategories_id"] = analysis.new_category_id

        payload = {"input": payload_input}
        response = self._make_request("PUT", f"Ticket/{ticket_id}", json=payload)

        if response is not None:
            self.logger.info(f"Chamado #{ticket_id} atualizado com sucesso.")
            return True

        self.logger.error(f"Falha ao atualizar o chamado #{ticket_id}.")
        return False

# =============================================================================
# LLM SERVICE (Sem alterações)
# =============================================================================
class LLMService:
    def __init__(self, config: LLMConfig):
        self.config = config; self.logger = logging.getLogger(__name__)

    def analyze_ticket(self, ticket: Ticket) -> Optional[LLMAnalysisResult]:
        self.logger.info(f"Analisando risco e título para o chamado #{ticket.id}")
        full_content = f"TÍTULO ATUAL: {ticket.title}\n\nDESCRIÇÃO: {ticket.content}"
        prompt = f"{self.config.analysis_prompt}\n\nCONTEÚDO DO CHAMADO:\n---\n{full_content}\n---\n\nJSON:"
        for api_url in self.config.api_urls:
            try:
                payload = {"model": self.config.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}, "format": "json"}
                response = requests.post(f"{api_url.strip()}/api/generate", json=payload, timeout=45)
                response.raise_for_status(); response_str = response.json().get("response", "").strip()
                if not response_str: continue
                response_json = json.loads(response_str)
                return LLMAnalysisResult(
                    priority=int(response_json.get("priority", 3)),
                    urgency=int(response_json.get("urgency", 3)),
                    new_title=str(response_json.get("new_title", ticket.title)).strip() or ticket.title,
                    new_category_id=int(response_json.get("new_category_id", 0)))
            except (requests.exceptions.RequestException, json.JSONDecodeError, TypeError, ValueError) as e:
                self.logger.error(f"Falha ao analisar chamado #{ticket.id} com a LLM em {api_url}. Erro: {e}")
        return None

# =============================================================================
# MAIN APPLICATION LOGIC
# =============================================================================
class TicketAssessorApp:
    def __init__(self):
        self.app_config = AppConfig.from_env()
        setup_logging(self.app_config.log_level)
        self.logger = logging.getLogger(__name__)
        self.glpi_service = GLPIService(GLPIConfig.from_env())
        self.llm_service = LLMService(LLMConfig.from_env())
        # ! NOVO - Define o caminho do arquivo de rastreamento
        self.processed_ids_path = "/tmp/processed_ids.txt"

    # ! NOVO - Método para carregar IDs do arquivo de texto
    def _load_processed_ids(self) -> Set[str]:
        """Carrega os IDs dos chamados já processados a partir de um arquivo de texto."""
        if not os.path.exists(self.processed_ids_path):
            return set()
        try:
            with open(self.processed_ids_path, 'r') as f:
                return {line.strip() for line in f if line.strip()}
        except IOError as e:
            self.logger.error(f"Não foi possível ler o arquivo de IDs processados: {e}")
            return set()

    # ! NOVO - Método para salvar um novo ID no arquivo de texto
    def _mark_as_processed(self, ticket_id: str) -> None:
        """Adiciona o ID de um chamado ao arquivo de rastreamento."""
        try:
            with open(self.processed_ids_path, 'a') as f:
                f.write(f"{ticket_id}\n")
            self.logger.info(f"Chamado #{ticket_id} marcado como processado no arquivo local.")
        except IOError as e:
            self.logger.error(f"Não foi possível escrever no arquivo de IDs processados: {e}")

    def run_assessment_cycle(self):
        self.logger.info("====== INICIANDO CICLO DE ANÁLISE DE CHAMADOS ======")
        if not self.glpi_service.session_token:
            self.logger.error("Ciclo de análise pulado. Não foi possível estabelecer uma sessão com o GLPI."); return

        try:
            # ! LÓGICA FINAL - Implementa o fluxo com arquivo de texto
            # 1. Carrega a lista de IDs já processados
            processed_ids = self._load_processed_ids()
            self.logger.info(f"Carregados {len(processed_ids)} IDs de chamados já processados.")

            # 2. Busca todos os chamados ativos no GLPI
            active_tickets = self.glpi_service.get_all_active_tickets()

            # 3. Filtra em memória para encontrar os que precisam de análise
            tickets_to_process = [ticket for ticket in active_tickets if ticket.id not in processed_ids]

            if not tickets_to_process:
                self.logger.info("Nenhum chamado novo para processar encontrado neste ciclo.")
                return

            self.logger.info(f"Encontrados {len(tickets_to_process)} chamados para processar.")
            for ticket in tickets_to_process:
                self.logger.info(f"Processando chamado #{ticket.id}: '{ticket.title}'")
                analysis = self.llm_service.analyze_ticket(ticket)

                if analysis:
                    # 4. Atualiza e, se tiver sucesso, marca como processado
                    success = self.glpi_service.update_ticket(ticket.id, analysis)
                    if success:
                        self._mark_as_processed(ticket.id)
                else:
                    self.logger.warning(f"Não foi possível obter a análise da LLM para o chamado #{ticket.id}.")

                time.sleep(5) # Pausa entre as análises
        except Exception as e:
            self.logger.error(f"Erro crítico durante o ciclo de análise: {e}", exc_info=True)
        finally:
            self.logger.info("====== CICLO DE ANÁLISE CONCLUÍDO ======")

# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    app = TicketAssessorApp()
    config = AppConfig.from_env()
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(app.run_assessment_cycle, 'interval', minutes=config.assessment_interval_minutes, next_run_time=datetime.now())
    logging.info(f"Serviço de Análise de Chamados iniciado. Ciclos a cada {config.assessment_interval_minutes} minutos.")
    try: scheduler.start()
    except (KeyboardInterrupt, SystemExit): logging.info("Serviço de Análise de Chamados encerrado.")
