# 🤖 GLPI Reclassification with LLM

Um projeto para automatizar a reclassificação de chamados no GLPI utilizando o poder de Modelos de Linguagem Grandes (LLMs). Este script analisa os títulos e descrições dos chamados, corrige erros de digitação, padroniza títulos e atribui a prioridade e urgência corretas com base em um conjunto de regras de negócio customizáveis.

![Status](https://img.shields.io/badge/status-funcional-green)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/licen%C3%A7a-MIT-lightgrey)

---

## 📖 Sobre o Projeto

A triagem e classificação manual de chamados em um sistema de help desk como o GLPI é uma tarefa repetitiva, demorada e sujeita a inconsistências. Diferentes analistas podem interpretar o mesmo chamado de maneiras distintas, resultando em prioridades desalinhadas e tempos de resposta inadequados.

Este projeto resolve esse problema utilizando uma LLM para analisar o conteúdo de cada chamado e sugerir uma nova classificação de forma padronizada e inteligente. O resultado é um conjunto de comandos SQL prontos para serem executados, atualizando os chamados no GLPI em lote.

## ✨ Funcionalidades

* **Reclassificação Inteligente:** Atribui prioridade e urgência com base na análise semântica do conteúdo do chamado.
* **Padronização de Títulos:** Cria títulos novos, claros e objetivos para os chamados.
* **Correção Automática:** Corrige pequenos erros de digitação nos títulos originais para melhor compreensão.
* **Alta Customização:** Toda a inteligência e as regras de negócio residem em um único prompt no arquivo `.env`, permitindo uma personalização completa sem alterar o código.

## ⚙️ Como Funciona

O fluxo de trabalho do projeto é simples e direto:

1.  **Obtem Chamados em Aberto:** Usando API REST do GLPI.
2.  **Análise:** O script Python lê cada linha do CSV.
3.  **Consulta à LLM:** Para cada chamado, o script envia o conteúdo para uma LLM (como Ollama, OpenAI, etc.) usando o prompt de análise definido no arquivo `.env`.
4.  **Recebimento do JSON:** A LLM retorna uma análise estruturada em formato JSON com o novo título, prioridade, urgência e categoria.
5.  **Execução:** Ao final, ele atualiza usando a API Rest


## 🛠️ Pré-requisitos

* Python 3.9 ou superior
* Acesso a um endpoint de uma LLM (ex: Ollama rodando localmente, API da OpenAI, etc.)
* Acesso de leitura/escrita ao banco de dados do seu GLPI.

## 🚀 Instalação e Configuração

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/c4pote/glpi_reclassificacao_llm.git](https://github.com/c4pote/glpi_reclassificacao_llm.git)
    cd glpi_reclassificacao_llm
    ```

2.  **Instale as dependências:**
    (Recomenda-se criar um ambiente virtual primeiro: `python -m venv venv` e `source venv/bin/activate`)
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure o ambiente:**
    Crie uma cópia do arquivo de exemplo `.env.example` e renomeie para `.env`.
    ```bash
    cp .env.example .env
    ```
    Agora, edite o arquivo `.env` com suas configurações. A variável mais importante é a `LLM_COMPREHENSIVE_ANALYSIS_PROMPT`.

## 🧠 O Coração do Projeto: O Prompt

Toda a "inteligência" desta automação está no prompt enviado para a LLM. Ele contém as regras de negócio, os critérios de prioridade e as instruções de formatação. Você pode (e deve!) ajustar este prompt para adequá-lo perfeitamente às necessidades da sua empresa.

<details>
<summary><strong>Clique para ver o prompt completo contido no .env</strong></summary>

```ini
LLM_COMPREHENSIVE_ANALYSIS_PROMPT="SYSTEM_TASK: Analise o ticket. Responda estritamente em JSON com as chaves: new_title, priority, urgency, new_category_id. Não inclua texto fora do objeto JSON.\n\nFIELD_RULES:\n- new_title: Crie um resumo técnico e objetivo. Importante: Corrija erros de digitação óbvios para preservar o significado original do texto (ex: 'probema' para 'problema', 'maguida' para 'máquina'). Não altere o tópico principal nem introduza conceitos que não estão no chamado.\n- priority: Use a escala de 1 a 5, baseada na Lógica de Prioridade abaixo.\n- urgency: Valor deve ser idêntico ao da priority.\n- new_category_id: ID da categoria correspondente. Use 0 se não for determinável.\n\nPRIORITY_LOGIC:\n\nPRIORITY 5 (Crítica): Interrupção total de serviço, risco de segurança ou bloqueio de operação de negócio essencial.\n- Keywords/Context - Segurança: falha grave, violação, ataque cibernético, incidente crítico.\n- Keywords/Context - Infraestrutura: servidores fora do ar, rede corporativa inoperante, sistemas essenciais inacessíveis.\n- Keywords/Context - Acesso/Certificados: erro de autenticação crítica, certificado SSL vencido bloqueando operações.\n- Keywords/Context - Sistemas de Negócio: falha em ERP ou API que impede faturamento, contabilidade, ou vendas.\n- Keywords/Context - Hardware/SO: máquina travada, falha no boot, sistema operacional corrompido, perda total de acesso.\n\nPRIORITY 4 (Alta): Impacto significativo no negócio, mas com alternativas temporárias ou efeito parcial.\n- Keywords/Context - Acesso/Permissões: limita usuários críticos, mas sem bloqueio total.\n- Keywords/Context - Infraestrutura: falha em serviços secundários, problemas de latência, servidor lento.\n- Keywords/Context - Hardware/Software: erros em máquinas de produção, equipamentos estratégicos.\n- Keywords/Context - Configuração: problemas que afetam o desempenho sem causar interrupção completa.\n\nPRIORITY 3 (Média): Ajustes, manutenção e melhorias necessárias que podem ser agendadas.\n- Keywords/Context - Sistemas de Negócio: correções em relatórios, ajustes em integrações.\n- Keywords/Context - Desenvolvimento: bugs menores, ajustes de código, pequenas falhas em APIs.\n- Keywords/Context - Automação/Scripts: revisões e melhorias que não impactam a operação imediatamente.\n- Keywords/Context - SO/Software: instalação de pacotes, otimizações, suporte avançado não urgente.\n\nPRIORITY 2 (Baixa): Suporte operacional, consultivo ou impacto em poucos usuários.\n- Keywords/Context - Suporte Nível 1: dúvidas básicas, orientações, treinamentos.\n- Keywords/Context - Aplicações: melhorias cosméticas, pequenas correções visuais.\n- Keywords/Context - Requisições: solicitações de acesso não urgentes, criação de novos usuários.\n\nPRIORITY 1 (Muito Baixa): Tarefas administrativas ou demandas de planejamento sem impacto operacional imediato.\n- Keywords/Context - Planejamento/Documentação: organização de tarefas, relatórios administrativos, registros.\n- Keywords/Context - Atualizações: melhorias futuras, ajustes em sistemas sem urgência.\n- Keywords/Context - Geral: pedidos de informações, consultas simples."
```

</details>

## 🏃 Como Executar

1.  **Prepare seus dados:** Exporte uma lista de chamados do GLPI para um arquivo `tickets.csv`. O arquivo deve conter no mínimo as colunas `id` e `titulo`.

2.  **Execute o script principal:**
    ```bash
    python main.py seu_arquivo.csv
    ```
    *Substitua `seu_arquivo.csv` pelo nome do seu arquivo exportado.*

3.  **Revise o resultado:** O script irá gerar um arquivo chamado `comandos_update.sql`. **É crucial revisar este arquivo** para garantir que as alterações fazem sentido antes de aplicá-las.

4.  **Aplique no banco de dados:**
    ⚠️ **IMPORTANTE:** Faça sempre um **backup** do seu banco de dados antes de executar scripts de atualização em massa!
    Execute o conteúdo do arquivo `comandos_update.sql` no seu banco de dados MySQL do GLPI.

## 🤝 Como Contribuir

Contribuições são bem-vindas! Se você tem ideias para melhorar o projeto, sinta-se à vontade para:

1.  Fazer um Fork do projeto.
2.  Criar uma nova Branch (`git checkout -b feature/sua-feature`).
3.  Fazer o Commit de suas mudanças (`git commit -m 'Adiciona sua-feature'`).
4.  Fazer o Push para a Branch (`git push origin feature/sua-feature`).
5.  Abrir um Pull Request.

## 📝 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
