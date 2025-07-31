#!/bin/bash

# --- Script de Instalação do GLPI Advanced Ticket Assessor ---

echo "🚀 Iniciando a instalação das dependências..."

# 1. Verifica se Python 3 e pip estão disponíveis
if ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
    echo "❌ Erro: Python 3 e/ou pip3 não encontrados. Por favor, instale-os para continuar."
    exit 1
fi
echo "✅ Python 3 e Pip encontrados."

# 2. Cria um ambiente virtual para isolar as dependências
if [ ! -d "venv" ]; then
    echo "🐍 Criando ambiente virtual na pasta 'venv'..."
    python3 -m venv venv
else
    echo "🐍 Ambiente virtual 'venv' já existe."
fi

# 3. Ativa o ambiente virtual
source venv/bin/activate
echo "✅ Ambiente virtual ativado."

# 4. Instala os pacotes a partir do requirements.txt
if [ -f "requirements.txt" ]; then
    echo "📦 Instalando pacotes..."
    pip3 install -r requirements.txt
    echo "✅ Pacotes instalados com sucesso!"
else
    echo "⚠️ Aviso: Arquivo requirements.txt não encontrado. A instalação foi pulada."
fi

echo ""
echo "🎉 Instalação concluída!"
echo ""
echo "👉 Próximos passos:"
echo "   1. Crie e configure o arquivo '.env' com suas chaves e URLs."
echo "   2. Para iniciar o servidor, execute o script: ./start.sh"
echo ""
