#!/bin/bash

# --- Script de Inicialização do GLPI Advanced Ticket Assessor ---

# Nome do arquivo principal da aplicação
APP_FILE="app.py"

echo "▶️  Iniciando a aplicação..."

# 1. Verifica a existência do arquivo de configuração .env
if [ ! -f ".env" ]; then
    echo "❌ Erro: O arquivo de configuração '.env' não foi encontrado."
    echo "   Por favor, crie o arquivo .env e preencha com suas credenciais antes de iniciar."
    exit 1
fi

# 2. Ativa o ambiente virtual, se existir
if [ -d "venv" ]; then
    echo "🐍 Ativando ambiente virtual..."
    source venv/bin/activate
else
    echo "⚠️ Aviso: Ambiente virtual 'venv' não encontrado. Usando o interpretador Python do sistema."
fi

# 3. Verifica se o script principal existe
if [ ! -f "$APP_FILE" ]; then
    echo "❌ Erro: O arquivo da aplicação '$APP_FILE' não foi encontrado neste diretório."
    exit 1
fi

# 4. Executa a aplicação Python
echo "🚀 Servidor iniciado! Pressione CTRL+C para parar."
python3 $APP_FILE
