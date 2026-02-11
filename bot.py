import logging
import json
import random
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ============================================================================
# CONFIGURAÇÃO RÁPIDA (EDITAR SÓ ESSAS LINHAS)
# ============================================================================
TOKEN = "7390135237:AAE1A6HoR90Cd_cKZ8AmFCBIYQkEJvdtsew"  # <-- COLOCA TEU TOKEN REAL AQUI
DONO_ID = 7752239017       # <-- TEU ID (DONO ÚNICO)
SUPORTE_LINK = "http://t.me/Scxttvoid_Bot"

# ============================================================================
# SETUP DE LOGS
# ============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# ESTRUTURAS DE DADOS GLOBAIS
# ============================================================================
usuarios: Dict[int, dict] = {}
numeros_disponiveis: List[str] = []
vendas_log: List[dict] = []
log_transacoes: List[dict] = []

# ADMs com hierarquia e permissões
adms: Dict[int, dict] = {
    DONO_ID: {
        "nome": "DONO",
        "cargo": "dono",
        "status": "online",
        "permissoes": {
            "todas": True
        },
        "estatisticas": {
            "operacoes": 0,
            "valor_total": 0.0,
            "bonus": 0.0
        }
    }
}

# Requisições de recarga em andamento (com timeout)
requisicoes_recarga: Dict[str, dict] = {}

# Solicitações de afiliado pendentes
solicitacoes_afiliado: Dict[int, dict] = {}

# Tickets de suporte
tickets: Dict[str, dict] = {}

# Configurações editáveis da interface
config_interface = {
    "titulo": "🔒 BIN STORE",
    "subtitulo": "🟢 Online • {} disponíveis",
    "mensagem_dia": "⚡ Entrega em até 2 minutos!",
    "avisos": [
        "⚠️ Compre apenas se tiver certeza",
        "❌ Sem reembolso após entrega"
    ],
    "dicas": [
        "💡 Use /start para atualizar",
        "🤝 Indique amigos e ganhe comissão"
    ]
}

# Configurações do sistema
config_sistema = {
    "precificacao": {
        "498555": 15.00,
        "512345": 25.00,
        "458763": 35.00,
        "543210": 20.00,
        "400000": 18.00,
        "555555": 30.00,
        "444444": 22.00,
        "511111": 28.00
    },
    "bin_nomes": {
        "498555": "💳 Visa Platinum",
        "512345": "💎 Mastercard Black",
        "458763": "🚀 Amex Gold",
        "543210": "⭐ Visa Classic",
        "400000": "🛡️ Mastercard Standard",
        "555555": "👑 Visa Infinite",
        "444444": "✨ Amex Blue",
        "511111": "🔥 Mastercard World"
    },
    "bin_destaque": ["498555", "512345"],
    "comissao_afiliado": 50.0,
    "bonus_recarga_ativo": False,
    "modo_manutencao": False,
    "modo_teste": False,
    "notificar_admin_compras": True,
    "notificar_grupo_compras": False,
    "chat_id_grupo": None,
    "limite_compras_hora": 5,
    "vendas_totais": 0,
    "ultimo_backup": ""
}

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================
def get_user_data(user_id: int, indicador_id: Optional[int] = None) -> dict:
    if user_id not in usuarios:
        usuarios[user_id] = {
            "nome": "",
            "saldo": 0.0,
            "ban": False,
            "compras": 0,
            "data_primeiro_uso": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "historico": [],
            "ultimo_comando": None,
            "indicador_id": indicador_id,
            "indicados": [],
            "afiliados_validos": 0,
            "saldo_afiliado": 0.0,
            "solicitou_afiliado": False,
            "afiliado_aprovado": False
        }
    
    if indicador_id and usuarios[user_id]["indicador_id"] is None:
        usuarios[user_id]["indicador_id"] = indicador_id
        if user_id not in usuarios.get(indicador_id, {}).get("indicados", []):
            usuarios[indicador_id]["indicados"].append(user_id)
            salvar_dados()
    
    return usuarios[user_id]

@lru_cache(maxsize=1)
def get_grupos() -> Dict[str, List[str]]:
    grupos = {}
    for num in numeros_disponiveis:
        prefixo = num.split('|')[0][:6]
        if prefixo not in grupos:
            grupos[prefixo] = []
        grupos[prefixo].append(num)
    return grupos

def mascara_numero(numero: str) -> str:
    partes = numero.split('|')
    cc = partes[0]
    mask_cc = cc[:6] + '••••••••••' + cc[-4:]
    return f"{mask_cc}|{partes[1]}|{partes[2]}|XXXX"

def preco_bin(prefixo: str) -> float:
    return config_sistema["precificacao"].get(prefixo, 15.00)

def nome_bin(prefixo: str) -> str:
    return config_sistema["bin_nomes"].get(prefixo, f"BIN {prefixo}")

def verificar_limite_compras(user_id: int) -> bool:
    user_data = get_user_data(user_id)
    agora = datetime.now()
    historico_recente = [
        h for h in user_data["historico"]
        if (agora - datetime.strptime(h["data"], "%d/%m/%Y %H:%M")).total_seconds() < 3600
    ]
    return len(historico_recente) < config_sistema["limite_compras_hora"]

def salvar_dados():
    try:
        dados = {
            'usuarios': usuarios,
            'numeros_disponiveis': numeros_disponiveis,
            'vendas_log': vendas_log,
            'log_transacoes': log_transacoes,
            'adms': adms,
            'requisicoes_recarga': requisicoes_recarga,
            'solicitacoes_afiliado': solicitacoes_afiliado,
            'tickets': tickets,
            'config_interface': config_interface,
            'config_sistema': config_sistema
        }
        with open('dados.json', 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        config_sistema["ultimo_backup"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    except Exception as e:
        logger.error(f"Erro ao salvar: {e}")

def carregar_dados():
    global usuarios, numeros_disponiveis, vendas_log, log_transacoes, adms
    global requisicoes_recarga, solicitacoes_afiliado, tickets, config_interface, config_sistema
    
    try:
        with open('dados.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            usuarios = dados.get('usuarios', {})
            numeros_disponiveis = dados.get('numeros_disponiveis', [])
            vendas_log = dados.get('vendas_log', [])
            log_transacoes = dados.get('log_transacoes', [])
            adms.update(dados.get('adms', {}))
            requisicoes_recarga = dados.get('requisicoes_recarga', {})
            solicitacoes_afiliado = dados.get('solicitacoes_afiliado', {})
            tickets = dados.get('tickets', {})
            config_interface.update(dados.get('config_interface', {}))
            config_sistema.update(dados.get('config_sistema', {}))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error(f"Erro ao carregar: {e}")

def registrar_transacao(tipo: str, dados: dict):
    transacao = {
        "id": f"LOG_{int(time.time())}",
        "tipo": tipo,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_formatada": datetime.now().strftime("%d/%m/%Y"),
        **dados
    }
    log_transacoes.append(transacao)
    salvar_dados()
    return transacao["id"]

def get_adm_permissao(user_id: int, permissao: str) -> bool:
    if user_id == DONO_ID:
        return True
    if user_id not in adms:
        return False
    if adms[user_id]["cargo"] == "dono":
        return True
    return adms[user_id]["permissoes"].get(permissao, False)

def formatar_moeda(valor: float) -> str:
    return f"R$ {valor:.2f}".replace('.', ',')

# ============================================================================
# SISTEMA DE REQUISIÇÕES DE RECARGA COM TIMEOUT
# ============================================================================
async def verificar_timeout_recargas(context: ContextTypes.DEFAULT_TYPE):
    agora = datetime.now()
    expiradas = []
    
    for req_id, req in list(requisicoes_recarga.items()):
        if req["status"] == "aguardando_adm":
            data_criacao = datetime.strptime(req["data_criacao"], "%Y-%m-%d %H:%M:%S")
            if (agora - data_criacao).total_seconds() > 60:  # 1 minuto
                expiradas.append(req_id)
                req["status"] = "expirada"
                try:
                    await context.bot.send_message(
                        chat_id=req["user_id"],
                        text="⚠️ <b>Nenhum ADM disponível no momento.</b>\nTente novamente em alguns minutos.",
                        parse_mode="HTML"
                    )
                except:
                    pass
    
    if expiradas:
        salvar_dados()

# ============================================================================
# HANDLERS PRINCIPAIS
# ============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    indicador_id = None
    if args and args[0].startswith("ref_"):
        try:
            indicador_id = int(args[0].replace("ref_", ""))
        except:
            pass
    
    user_data = get_user_data(user.id, indicador_id)
    user_data["nome"] = user.full_name
    
    if config_sistema["modo_manutencao"] and user.id != DONO_ID and not get_adm_permissao(user.id, "todas"):
        await update.message.reply_text(
            "⚠️ <b>O bot está em manutenção.</b>\nVolte mais tarde!",
            parse_mode="HTML"
        )
        return
    
    # Montar mensagem com interface editável
    msg = f"┏━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    msg += f"   {config_interface['titulo']}\n"
    msg += f"   {config_interface['subtitulo'].format(len(numeros_disponiveis))}\n"
    msg += f"   ✅ {config_sistema['vendas_totais']} vendas\n"
    msg += f"┗━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
    
    if config_interface["mensagem_dia"]:
        msg += f"📢 {config_interface['mensagem_dia']}\n\n"
    
    if config_interface["avisos"]:
        msg += "⚠️ <b>AVISOS:</b>\n"
        for aviso in config_interface["avisos"]:
            msg += f"• {aviso}\n"
        msg += "\n"
    
    if config_interface["dicas"]:
        msg += "💡 <b>DICAS:</b>\n"
        for dica in config_interface["dicas"]:
            msg += f"• {dica}\n"
        msg += "\n"
    
    msg += f"Olá, {user.first_name}! 👋\nEscolha uma opção abaixo:"
    
    # Menu dinâmico baseado em permissões
    botoes = [
        [InlineKeyboardButton("💳 Comprar", callback_data="comprar_inicio")]
    ]
    
    if user_data.get("afiliado_aprovado", False):
        botoes.append([InlineKeyboardButton("🤝 Afiliados", callback_data="menu_afiliados")])
    else:
        botoes.append([InlineKeyboardButton("🤝 Quero ser Afiliado", callback_data="solicitar_afiliado")])
    
    botoes.append([InlineKeyboardButton("👤 Minha Conta", callback_data="menu_perfil")])
    
    # ADMs veem botão extra
    if user.id in adms and adms[user.id]["status"] == "online":
        botoes.append([InlineKeyboardButton("👑 Painel ADM", callback_data="painel_adm")])
    
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def solicitar_afiliado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if user_data["solicitou_afiliado"]:
        await query.answer("⚠️ Você já solicitou para ser afiliado. Aguarde aprovação.", show_alert=True)
        return
    
    if user_data["afiliado_aprovado"]:
        await query.answer("✅ Você já é afiliado!", show_alert=True)
        return
    
    user_data["solicitou_afiliado"] = True
    salvar_dados()
    
    # Notificar ADMs com permissão
    notificacao = (
        f"🆕 <b>NOVA SOLICITAÇÃO DE AFILIADO</b>\n\n"
        f"Usuário: {user_data['nome']} (ID: {user_id})\n"
        f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Use o painel ADM para aprovar ou recusar."
    )
    
    for adm_id, adm in adms.items():
        if adm["status"] == "online" and get_adm_permissao(adm_id, "aceitar_afiliado"):
            try:
                await context.bot.send_message(chat_id=adm_id, text=notificacao, parse_mode="HTML")
            except:
                pass
    
    registrar_transacao("solicitacao_afiliado", {
        "user_id": user_id,
        "user_nome": user_data["nome"]
    })
    
    await query.edit_message_text(
        "✅ <b>Solicitação enviada!</b>\n\n"
        "Aguarde aprovação de um ADM.\nVocê será notificado quando sua solicitação for analisada.",
        parse_mode="HTML"
    )

async def menu_afiliados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data.get("afiliado_aprovado", False):
        await query.edit_message_text(
            "⚠️ <b>Você não é afiliado ainda.</b>\n\n"
            "Solicite acesso em '🤝 Quero ser Afiliado' no menu principal.",
            parse_mode="HTML"
        )
        return
    
    link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    
    total_ganho = user_data.get("saldo_afiliado", 0.0)
    total_indicados = len(user_data.get("indicados", []))
    validos = user_data.get("afiliados_validos", 0)
    
    msg = (
        f"🤝 <b>SEU PROGRAMA DE AFILIADOS</b>\n\n"
        f"💰 Comissão: {config_sistema['comissao_afiliado']}%\n"
        f"🤑 Saldo de Afiliado: {formatar_moeda(total_ganho)}\n"
        f"👥 Indicados: {total_indicados}\n"
        f"✅ Afiliados Válidos: {validos}\n\n"
        f"🔗 <b>Seu link único:</b>\n"
        f"<code>{link}</code>\n\n"
        f"⚠️ <b>Afiliado Válido</b>: Indicado que recarregou saldo\n"
        f"🎁 <b>Bônus</b>: R$ 5,00 por afiliado válido"
    )
    
    botoes = [
        [InlineKeyboardButton("💰 Converter Saldo", callback_data="converter_saldo_afiliado")],
        [InlineKeyboardButton("📤 Vender Afiliados Válidos", callback_data="vender_afiliados_validos")],
        [InlineKeyboardButton("🔄 Atualizar", callback_data="menu_afiliados")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="voltar_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)

async def converter_saldo_afiliado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if user_data["saldo_afiliado"] <= 0:
        await query.answer("⚠️ Saldo de afiliado insuficiente!", show_alert=True)
        return
    
    valor = user_data["saldo_afiliado"]
    user_data["saldo"] += valor
    user_data["saldo_afiliado"] = 0.0
    salvar_dados()
    
    registrar_transacao("conversao_saldo_afiliado", {
        "user_id": user_id,
        "user_nome": user_data["nome"],
        "valor": valor
    })
    
    await query.edit_message_text(
        f"✅ <b>Saldo convertido com sucesso!</b>\n\n"
        f"💰 {formatar_moeda(valor)} transferido para seu saldo principal.\n"
        f"💵 Saldo atual: {formatar_moeda(user_data['saldo'])}",
        parse_mode="HTML"
    )

async def vender_afiliados_validos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    validos = user_data.get("afiliados_validos", 0)
    if validos <= 0:
        await query.answer("⚠️ Você não tem afiliados válidos para vender!", show_alert=True)
        return
    
    valor_total = validos * 5.00
    
    msg = (
        f"📤 <b>VENDER AFILIADOS VÁLIDOS</b>\n\n"
        f"✅ Afiliados Válidos: {validos}\n"
        f"💰 Valor total: {formatar_moeda(valor_total)}\n\n"
        f"⚠️ Ao vender, você perderá todos os afiliados válidos.\n"
        f"O valor será creditado após aprovação de um ADM."
    )
    
    botoes = [
        [InlineKeyboardButton("✅ Confirmar Venda", callback_data=f"confirmar_venda_afiliados_{validos}")],
        [InlineKeyboardButton("↩️ Cancelar", callback_data="menu_afiliados")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def confirmar_venda_afiliados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    validos = int(query.data.replace("confirmar_venda_afiliados_", ""))
    valor_total = validos * 5.00
    
    # Criar requisição de venda
    req_id = f"VENDA_{int(time.time())}"
    requisicoes_recarga[req_id] = {
        "id": req_id,
        "tipo": "venda_afiliados",
        "user_id": user_id,
        "user_nome": user_data["nome"],
        "quantidade": validos,
        "valor": valor_total,
        "status": "aguardando_adm",
        "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "adm_responsavel": None
    }
    salvar_dados()
    
    # Notificar ADMs
    notificacao = (
        f"📤 <b>NOVA VENDA DE AFILIADOS</b>\n\n"
        f"ID: {req_id}\n"
        f"Usuário: {user_data['nome']} (ID: {user_id})\n"
        f"Quantidade: {validos} afiliados válidos\n"
        f"Valor: {formatar_moeda(valor_total)}\n\n"
        f"[ ✅ Aceitar ] [ ❌ Recusar ]"
    )
    
    teclado_adm = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceitar", callback_data=f"aceitar_venda_{req_id}")],
        [InlineKeyboardButton("❌ Recusar", callback_data=f"recusar_venda_{req_id}")]
    ])
    
    for adm_id, adm in adms.items():
        if adm["status"] == "online" and get_adm_permissao(adm_id, "vender_afiliados"):
            try:
                await context.bot.send_message(
                    chat_id=adm_id,
                    text=notificacao,
                    reply_markup=teclado_adm,
                    parse_mode="HTML"
                )
            except:
                pass
    
    registrar_transacao("venda_afiliados_solicitada", {
        "req_id": req_id,
        "user_id": user_id,
        "user_nome": user_data["nome"],
        "quantidade": validos,
        "valor": valor_total
    })
    
    await query.edit_message_text(
        f"✅ <b>Solicitação enviada!</b>\n\n"
        f"ID: {req_id}\n"
        f"Valor: {formatar_moeda(valor_total)}\n\n"
        f"Aguarde aprovação de um ADM.\nVocê será notificado quando processado.",
        parse_mode="HTML"
    )

# ============================================================================
# SISTEMA DE ADMs - PAINEL E OPERAÇÕES
# ============================================================================
async def painel_adm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in adms or adms[user_id]["status"] != "online":
        await query.answer("⚠️ Você não é ADM ou está offline.", show_alert=True)
        return
    
    adm = adms[user_id]
    stats = adm["estatisticas"]
    
    msg = (
        f"👑 <b>PAINEL ADM - {adm['nome']}</b>\n\n"
        f"💼 Cargo: {adm['cargo'].title()}\n"
        f"🟢 Status: Online\n\n"
        f"📊 ESTATÍSTICAS\n"
        f"   Operações: {stats['operacoes']}\n"
        f"   Valor total: {formatar_moeda(stats['valor_total'])}\n"
        f"   Bônus: {formatar_moeda(stats['bonus'])}\n\n"
    )
    
    # Requisições pendentes
    pendentes = [
        req for req in requisicoes_recarga.values()
        if req["status"] == "aguardando_adm"
    ]
    
    if pendentes:
        msg += f"📥 REQUISIÇÕES PENDENTES ({len(pendentes)})\n"
        for req in pendentes[:3]:  # Mostrar só 3
            if req.get("tipo") == "venda_afiliados":
                msg += f"• {req['id']} - Venda {req['quantidade']} afiliados - {formatar_moeda(req['valor'])}\n"
            else:
                msg += f"• {req['id']} - {req['user_nome']} - {formatar_moeda(req['valor'])}\n"
        if len(pendentes) > 3:
            msg += f"... e mais {len(pendentes) - 3}\n"
        msg += "\n"
    
    botoes = [
        [InlineKeyboardButton("📥 Ver Requisições", callback_data="ver_requisicoes")],
        [InlineKeyboardButton("🎫 Tickets", callback_data="menu_tickets")],
    ]
    
    # Só dono/gerente veem controle total
    if user_id == DONO_ID or adm["cargo"] == "gerente":
        botoes.append([InlineKeyboardButton("⚙️ Controle Total", callback_data="controle_total")])
    
    botoes.append([InlineKeyboardButton("🔴 Ficar Offline", callback_data="ficar_offline")])
    
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def ver_requisicoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in adms or adms[user_id]["status"] != "online":
        await query.answer("⚠️ Você não é ADM ou está offline.", show_alert=True)
        return
    
    pendentes = [
        req for req in requisicoes_recarga.values()
        if req["status"] == "aguardando_adm"
    ]
    
    if not pendentes:
        await query.edit_message_text(
            "✅ <b>Nenhuma requisição pendente no momento.</b>",
            parse_mode="HTML"
        )
        return
    
    msg = "📥 <b>REQUISIÇÕES PENDENTES</b>\n\n"
    botoes = []
    
    for req in pendentes[:10]:  # Máximo 10
        if req.get("tipo") == "venda_afiliados":
            label = f"📤 {req['id']} - {req['quantidade']} afiliados"
        else:
            label = f"💰 {req['id']} - {req['user_nome']} - {formatar_moeda(req['valor'])}"
        
        botoes.append([
            InlineKeyboardButton("✅", callback_data=f"aceitar_req_{req['id']}"),
            InlineKeyboardButton("❌", callback_data=f"recusar_req_{req['id']}"),
            InlineKeyboardButton(label, callback_data=f"detalhes_req_{req['id']}")
        ])
    
    botoes.append([InlineKeyboardButton("↩️ Voltar", callback_data="painel_adm")])
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def aceitar_requisicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    req_id = query.data.replace("aceitar_req_", "")
    
    if req_id not in requisicoes_recarga:
        await query.answer("❌ Requisição não encontrada.", show_alert=True)
        return
    
    req = requisicoes_recarga[req_id]
    
    if req["status"] != "aguardando_adm":
        await query.answer("⚠️ Requisição já processada.", show_alert=True)
        return
    
    req["status"] = "aceita"
    req["adm_responsavel"] = user_id
    req["data_aceite"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Atualizar estatísticas do ADM
    if user_id in adms:
        adms[user_id]["estatisticas"]["operacoes"] += 1
        if req.get("tipo") != "venda_afiliados":
            adms[user_id]["estatisticas"]["valor_total"] += req["valor"]
    
    salvar_dados()
    
    # Notificar usuário
    if req.get("tipo") == "venda_afiliados":
        msg_user = (
            f"✅ <b>Venda de Afiliados Aceita!</b>\n\n"
            f"ID: {req_id}\n"
            f"Quantidade: {req['quantidade']} afiliados válidos\n"
            f"Valor: {formatar_moeda(req['valor'])}\n\n"
            f"⚠️ Seus afiliados válidos foram removidos.\n"
            f"O valor será creditado em breve."
        )
        
        # Remover afiliados válidos do usuário
        user_data = get_user_data(req["user_id"])
        user_data["afiliados_validos"] = 0
        user_data["saldo_afiliado"] += req["valor"]  # Creditar saldo de afiliado
        salvar_dados()
        
        registrar_transacao("venda_afiliados_aceita", {
            "req_id": req_id,
            "user_id": req["user_id"],
            "user_nome": req["user_nome"],
            "adm_id": user_id,
            "adm_nome": adms[user_id]["nome"],
            "quantidade": req["quantidade"],
            "valor": req["valor"]
        })
    else:
        msg_user = (
            f"✅ <b>Requisição de Recarga Aceita!</b>\n\n"
            f"ID: {req_id}\n"
            f"Valor: {formatar_moeda(req['valor'])}\n\n"
            f"Aguarde o ADM enviar a chave PIX para pagamento."
        )
    
    try:
        await context.bot.send_message(
            chat_id=req["user_id"],
            text=msg_user,
            parse_mode="HTML"
        )
    except:
        pass
    
    # Notificar ADM para enviar chave PIX
    if req.get("tipo") != "venda_afiliados":
        msg_adm = (
            f"🔑 <b>ENVIE A CHAVE PIX</b>\n\n"
            f"Requisição: {req_id}\n"
            f"Usuário: {req['user_nome']} (ID: {req['user_id']})\n"
            f"Valor: {formatar_moeda(req['valor'])}\n\n"
            f"Use o comando:\n"
            f"<code>/cobrar {req_id} SUA_CHAVE_PIX</code>"
        )
        await query.edit_message_text(msg_adm, parse_mode="HTML")
    else:
        await query.edit_message_text(
            f"✅ <b>Venda aceita com sucesso!</b>\n\n"
            f"ID: {req_id}\n"
            f"Usuário: {req['user_nome']}\n"
            f"Valor creditado: {formatar_moeda(req['valor'])}",
            parse_mode="HTML"
        )
    
    registrar_transacao("recarga_aceita", {
        "req_id": req_id,
        "user_id": req["user_id"],
        "user_nome": req["user_nome"],
        "valor": req["valor"],
        "adm_id": user_id,
        "adm_nome": adms[user_id]["nome"]
    })

async def recusar_requisicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    req_id = query.data.replace("recusar_req_", "")
    
    if req_id not in requisicoes_recarga:
        await query.answer("❌ Requisição não encontrada.", show_alert=True)
        return
    
    req = requisicoes_recarga[req_id]
    
    if req["status"] != "aguardando_adm":
        await query.answer("⚠️ Requisição já processada.", show_alert=True)
        return
    
    req["status"] = "recusada"
    req["adm_responsavel"] = user_id
    req["data_recusa"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    salvar_dados()
    
    # Notificar usuário
    try:
        await context.bot.send_message(
            chat_id=req["user_id"],
            text=(
                f"❌ <b>Requisição Recusada</b>\n\n"
                f"ID: {req_id}\n"
                f"Valor: {formatar_moeda(req['valor'])}\n\n"
                f"Um ADM recusou sua solicitação.\n"
                f"Tente novamente mais tarde."
            ),
            parse_mode="HTML"
        )
    except:
        pass
    
    await query.edit_message_text(
        f"✅ <b>Requisição recusada com sucesso!</b>\n\nID: {req_id}",
        parse_mode="HTML"
    )
    
    registrar_transacao("recarga_recusada", {
        "req_id": req_id,
        "user_id": req["user_id"],
        "user_nome": req["user_nome"],
        "valor": req["valor"],
        "adm_id": user_id,
        "adm_nome": adms[user_id]["nome"]
    })

async def cobrar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in adms or adms[user_id]["status"] != "online":
        await update.message.reply_text("⚠️ Você não é ADM ou está offline.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "Use: /cobrar <ID_REQUISICAO> <CHAVE_PIX>\n"
            "Ex: /cobrar REQ_123456 123456789@pix.com"
        )
        return
    
    req_id = context.args[0]
    chave_pix = context.args[1]
    
    if req_id not in requisicoes_recarga:
        await update.message.reply_text("❌ Requisição não encontrada.")
        return
    
    req = requisicoes_recarga[req_id]
    
    if req["status"] != "aceita" or req["adm_responsavel"] != user_id:
        await update.message.reply_text("⚠️ Você não é responsável por esta requisição.")
        return
    
    req["chave_pix"] = chave_pix
    req["status"] = "aguardando_pagamento"
    salvar_dados()
    
    # Enviar chave PIX pro usuário
    try:
        await context.bot.send_message(
            chat_id=req["user_id"],
            text=(
                f"💰 <b>PAGAMENTO SOLICITADO</b>\n\n"
                f"ID: {req_id}\n"
                f"Valor: {formatar_moeda(req['valor'])}\n"
                f"Chave PIX: <code>{chave_pix}</code>\n\n"
                f"⚠️ Após pagar, aguarde confirmação do ADM.\n"
                f"Não envie comprovante — o ADM verificará diretamente."
            ),
            parse_mode="HTML"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ <b>Chave PIX enviada!</b>\n\n"
        f"ID: {req_id}\n"
        f"Usuário: {req['user_nome']}\n"
        f"Valor: {formatar_moeda(req['valor'])}\n\n"
        f"Use /pago {req_id} para confirmar pagamento.",
        parse_mode="HTML"
    )
    
    registrar_transacao("pix_enviado", {
        "req_id": req_id,
        "user_id": req["user_id"],
        "user_nome": req["user_nome"],
        "valor": req["valor"],
        "adm_id": user_id,
        "adm_nome": adms[user_id]["nome"],
        "chave_pix": chave_pix[:20] + "..." if len(chave_pix) > 20 else chave_pix
    })

async def pago_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in adms or adms[user_id]["status"] != "online":
        await update.message.reply_text("⚠️ Você não é ADM ou está offline.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Use: /pago <ID_REQUISICAO>")
        return
    
    req_id = context.args[0]
    
    if req_id not in requisicoes_recarga:
        await update.message.reply_text("❌ Requisição não encontrada.")
        return
    
    req = requisicoes_recarga[req_id]
    
    if req["status"] != "aguardando_pagamento" or req["adm_responsavel"] != user_id:
        await update.message.reply_text("⚠️ Você não é responsável por esta requisição ou ela não está aguardando pagamento.")
        return
    
    # Creditar saldo ao usuário
    user_data = get_user_data(req["user_id"])
    user_data["saldo"] += req["valor"]
    
    # Atualizar estatísticas do ADM
    adms[user_id]["estatisticas"]["bonus"] += req["valor"] * 0.5  # 50% de bonus
    
    req["status"] = "paga"
    req["data_pagamento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    salvar_dados()
    
    # Notificar usuário
    try:
        await context.bot.send_message(
            chat_id=req["user_id"],
            text=(
                f"✅ <b>PAGAMENTO CONFIRMADO!</b>\n\n"
                f"ID: {req_id}\n"
                f"Valor: {formatar_moeda(req['valor'])}\n\n"
                f"💰 Seu saldo foi creditado!\n"
                f"Saldo atual: {formatar_moeda(user_data['saldo'])}"
            ),
            parse_mode="HTML"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ <b>Pagamento confirmado!</b>\n\n"
        f"ID: {req_id}\n"
        f"Usuário: {req['user_nome']}\n"
        f"Valor: {formatar_moeda(req['valor'])}\n"
        f"Seu bônus: {formatar_moeda(req['valor'] * 0.5)}",
        parse_mode="HTML"
    )
    
    registrar_transacao("recarga_paga", {
        "req_id": req_id,
        "user_id": req["user_id"],
        "user_nome": req["user_nome"],
        "valor": req["valor"],
        "adm_id": user_id,
        "adm_nome": adms[user_id]["nome"],
        "bonus_adm": req["valor"] * 0.5
    })

# ============================================================================
# PAINEL DONO - CONTROLE TOTAL E ESTATÍSTICAS
# ============================================================================
async def controle_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id != DONO_ID:
        await query.answer("⚠️ Acesso restrito ao dono.", show_alert=True)
        return
    
    msg = "👑 <b>CONTROLE TOTAL</b>\n\nEscolha uma opção:"
    
    botoes = [
        [InlineKeyboardButton("👥 Gerenciar ADMs", callback_data="gerenciar_adms")],
        [InlineKeyboardButton("🎨 Editar Interface", callback_data="editar_interface")],
        [InlineKeyboardButton("📊 Estatísticas", callback_data="estatisticas_menu")],
        [InlineKeyboardButton("📋 Logs", callback_data="ver_logs")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="painel_adm")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def gerenciar_adms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id != DONO_ID:
        await query.answer("⚠️ Acesso restrito ao dono.", show_alert=True)
        return
    
    msg = "👥 <b>GERENCIAR ADMs</b>\n\n"
    botoes = []
    
    for adm_id, adm in adms.items():
        if adm_id == DONO_ID:
            continue
        
        status = "🟢" if adm["status"] == "online" else "🔴"
        msg += f"{status} {adm['nome']} (ID: {adm_id}) - {adm['cargo'].title()}\n"
        botoes.append([
            InlineKeyboardButton("✏️", callback_data=f"editar_adm_{adm_id}"),
            InlineKeyboardButton("🚫", callback_data=f"remover_adm_{adm_id}"),
            InlineKeyboardButton(adm['nome'], callback_data=f"ver_adm_{adm_id}")
        ])
    
    botoes.append([InlineKeyboardButton("➕ Adicionar ADM", callback_data="adicionar_adm")])
    botoes.append([InlineKeyboardButton("↩️ Voltar", callback_data="controle_total")])
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def adicionar_adm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["aguardando_id_adm"] = True
    
    msg = (
        "➕ <b>ADICIONAR NOVO ADM</b>\n\n"
        "Envie o ID do usuário que deseja tornar ADM:"
    )
    
    botoes = [[InlineKeyboardButton("↩️ Cancelar", callback_data="gerenciar_adms")]]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def receber_id_adm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    
    if not context.user_data.get("aguardando_id_adm"):
        return
    
    try:
        user_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ ID inválido. Envie um número inteiro.")
        return
    
    if user_id in adms:
        await update.message.reply_text("⚠️ Este usuário já é ADM.")
        context.user_data.pop("aguardando_id_adm", None)
        return
    
    # Criar ADM padrão
    adms[user_id] = {
        "nome": f"ADM {user_id}",
        "cargo": "adm",
        "status": "offline",
        "permissoes": {
            "aceitar_recarga": True,
            "recusar_recarga": True,
            "aceitar_afiliado": True,
            "recusar_afiliado": True,
            "vender_afiliados": False,
            "abrir_ticket": True,
            "resolver_ticket": False
        },
        "estatisticas": {
            "operacoes": 0,
            "valor_total": 0.0,
            "bonus": 0.0
        }
    }
    salvar_dados()
    
    context.user_data.pop("aguardando_id_adm", None)
    
    await update.message.reply_text(
        f"✅ <b>ADM adicionado com sucesso!</b>\n\n"
        f"ID: {user_id}\n"
        f"Cargo: ADM\n\n"
        f"O usuário precisa mandar /start e clicar em '👑 Painel ADM' para ativar.",
        parse_mode="HTML"
    )

async def editar_interface(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id != DONO_ID:
        await query.answer("⚠️ Acesso restrito ao dono.", show_alert=True)
        return
    
    msg = "🎨 <b>EDITAR INTERFACE PRINCIPAL</b>\n\n"
    msg += f"📌 Título atual: {config_interface['titulo']}\n"
    msg += f"📌 Subtítulo atual: {config_interface['subtitulo']}\n"
    msg += f"📌 Mensagem do dia: {config_interface['mensagem_dia']}\n\n"
    msg += "Escolha o que editar:"
    
    botoes = [
        [InlineKeyboardButton("✏️ Título", callback_data="editar_titulo")],
        [InlineKeyboardButton("✏️ Subtítulo", callback_data="editar_subtitulo")],
        [InlineKeyboardButton("✏️ Mensagem do Dia", callback_data="editar_msg_dia")],
        [InlineKeyboardButton("✏️ Avisos", callback_data="editar_avisos")],
        [InlineKeyboardButton("✏️ Dicas", callback_data="editar_dicas")],
        [InlineKeyboardButton("💾 Salvar", callback_data="salvar_interface")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="controle_total")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def receber_edicao_interface(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    
    campo = context.user_data.get("editando_interface")
    if not campo:
        return
    
    valor = update.message.text.strip()
    
    if campo == "titulo":
        config_interface["titulo"] = valor
    elif campo == "subtitulo":
        config_interface["subtitulo"] = valor
    elif campo == "mensagem_dia":
        config_interface["mensagem_dia"] = valor
    elif campo == "aviso_novo":
        config_interface["avisos"].append(valor)
    elif campo == "dica_nova":
        config_interface["dicas"].append(valor)
    
    context.user_data.pop("editando_interface", None)
    salvar_dados()
    
    await update.message.reply_text(f"✅ {campo.title()} atualizado com sucesso!")

# ============================================================================
# ESTATÍSTICAS PERSONALIZADAS POR PERÍODO
# ============================================================================
def filtrar_logs_por_periodo(logs, data_inicial=None, data_final=None):
    if not data_inicial and not data_final:
        return logs
    
    logs_filtrados = []
    
    for log in logs:
        data_log = datetime.strptime(log["data_formatada"], "%d/%m/%Y")
        
        if data_inicial:
            data_ini = datetime.strptime(data_inicial, "%d/%m/%Y")
            if data_log < data_ini:
                continue
        
        if data_final:
            data_fim = datetime.strptime(data_final, "%d/%m/%Y")
            if data_log > data_fim:
                continue
        
        logs_filtrados.append(log)
    
    return logs_filtrados

def get_top_clientes(logs_filtrados, limite=10):
    clientes = {}
    
    for log in logs_filtrados:
        if log["tipo"] == "recarga_paga":
            user_id = log["user_id"]
            user_nome = log["user_nome"]
            valor = log["valor"]
            
            if user_id not in clientes:
                clientes[user_id] = {
                    "nome": user_nome,
                    "valor_total": 0,
                    "operacoes": 0
                }
            
            clientes[user_id]["valor_total"] += valor
            clientes[user_id]["operacoes"] += 1
    
    top = sorted(clientes.items(), key=lambda x: x[1]["valor_total"], reverse=True)[:limite]
    return top

def get_top_adms(logs_filtrados, limite=10):
    adms_stats = {}
    
    for log in logs_filtrados:
        if log["tipo"] == "recarga_paga":
            adm_id = log["adm_id"]
            adm_nome = log["adm_nome"]
            valor = log["valor"]
            
            if adm_id not in adms_stats:
                adms_stats[adm_id] = {
                    "nome": adm_nome,
                    "operacoes": 0,
                    "valor_total": 0
                }
            
            adms_stats[adm_id]["operacoes"] += 1
            adms_stats[adm_id]["valor_total"] += valor
    
    top = sorted(adms_stats.items(), key=lambda x: x[1]["operacoes"], reverse=True)[:limite]
    return top

def get_faturamento_por_dia(logs_filtrados):
    faturamento = {}
    
    for log in logs_filtrados:
        if log["tipo"] == "recarga_paga":
            data = log["data_formatada"]
            valor = log["valor"]
            
            if data not in faturamento:
                faturamento[data] = {"valor": 0, "operacoes": 0}
            
            faturamento[data]["valor"] += valor
            faturamento[data]["operacoes"] += 1
    
    return dict(sorted(faturamento.items()))

async def estatisticas_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id != DONO_ID:
        await query.answer("⚠️ Acesso restrito ao dono.", show_alert=True)
        return
    
    # Período padrão: últimos 7 dias
    data_final = datetime.now()
    data_inicial = data_final - timedelta(days=7)
    
    context.user_data["periodo_estatisticas"] = {
        "inicio": data_inicial.strftime("%d/%m/%Y"),
        "fim": data_final.strftime("%d/%m/%Y")
    }
    
    await mostrar_estatisticas(update, context)

async def mostrar_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    periodo = context.user_data.get("periodo_estatisticas", {
        "inicio": (datetime.now() - timedelta(days=7)).strftime("%d/%m/%Y"),
        "fim": datetime.now().strftime("%d/%m/%Y")
    })
    
    logs_filtrados = filtrar_logs_por_periodo(
        log_transacoes,
        periodo["inicio"],
        periodo["fim"]
    )
    
    # Calcular estatísticas
    faturamento_total = sum(log["valor"] for log in logs_filtrados if log["tipo"] == "recarga_paga")
    operacoes_total = sum(1 for log in logs_filtrados if log["tipo"] == "recarga_paga")
    top_clientes = get_top_clientes(logs_filtrados, 5)
    top_adms = get_top_adms(logs_filtrados, 5)
    faturamento_dia = get_faturamento_por_dia(logs_filtrados)
    
    # Montar mensagem
    msg = f"📊 <b>ESTATÍSTICAS PERSONALIZADAS</b>\n\n"
    msg += f"📅 Período: {periodo['inicio']} a {periodo['fim']}\n\n"
    
    msg += f"💰 <b>RESUMO FINANCEIRO</b>\n"
    msg += f"   Faturamento Total: {formatar_moeda(faturamento_total)}\n"
    msg += f"   Total ADMs (50%): {formatar_moeda(faturamento_total * 0.5)}\n"
    msg += f"   Total Dono (50%): {formatar_moeda(faturamento_total * 0.5)}\n"
    msg += f"   Operações: {operacoes_total}\n\n"
    
    msg += f"📈 <b>FATURAMENTO POR DIA</b>\n"
    for data, dados in list(faturamento_dia.items())[:7]:  # Últimos 7 dias
        msg += f"   • {data} - {formatar_moeda(dados['valor'])} ({dados['operacoes']} ops)\n"
    if len(faturamento_dia) > 7:
        msg += f"   ... e mais {len(faturamento_dia) - 7} dias\n\n"
    else:
        msg += "\n"
    
    msg += f"🏆 <b>TOP CLIENTES</b>\n"
    for i, (user_id, dados) in enumerate(top_clientes, 1):
        medalha = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        msg += f"   {medalha} {dados['nome']} - {formatar_moeda(dados['valor_total'])} ({dados['operacoes']} compras)\n"
    msg += "\n"
    
    msg += f"🎖️ <b>TOP ADMs</b>\n"
    for i, (adm_id, dados) in enumerate(top_adms, 1):
        medalha = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        bonus = dados['valor_total'] * 0.5
        msg += f"   {medalha} {dados['nome']} - {dados['operacoes']} ops | {formatar_moeda(bonus)} bonus\n"
    
    botoes = [
        [InlineKeyboardButton("✏️ Alterar Período", callback_data="alterar_periodo")],
        [InlineKeyboardButton("📥 Exportar CSV", callback_data="exportar_csv")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="controle_total")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    if query:
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def alterar_periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    hoje = datetime.now().strftime("%d/%m/%Y")
    semana_passada = (datetime.now() - timedelta(days=7)).strftime("%d/%m/%Y")
    mes_passado = (datetime.now() - timedelta(days=30)).strftime("%d/%m/%Y")
    
    msg = "📅 <b>SELECIONAR PERÍODO</b>\n\n"
    msg += "Períodos rápidos:\n"
    
    botoes = [
        [InlineKeyboardButton("Hoje", callback_data=f"periodo_hoje")],
        [InlineKeyboardButton("Esta Semana", callback_data=f"periodo_semana")],
        [InlineKeyboardButton("Este Mês", callback_data=f"periodo_mes")],
        [InlineKeyboardButton("Período Todo", callback_data=f"periodo_todo")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="estatisticas_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def definir_periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tipo = query.data.replace("periodo_", "")
    
    agora = datetime.now()
    
    if tipo == "hoje":
        inicio = agora.strftime("%d/%m/%Y")
        fim = inicio
    elif tipo == "semana":
        inicio = (agora - timedelta(days=7)).strftime("%d/%m/%Y")
        fim = agora.strftime("%d/%m/%Y")
    elif tipo == "mes":
        inicio = (agora - timedelta(days=30)).strftime("%d/%m/%Y")
        fim = agora.strftime("%d/%m/%Y")
    elif tipo == "todo":
        inicio = None
        fim = None
    else:
        await query.answer("⚠️ Período inválido.", show_alert=True)
        return
    
    context.user_data["periodo_estatisticas"] = {
        "inicio": inicio,
        "fim": fim
    }
    
    await mostrar_estatisticas(update, context)

# ============================================================================
# COMANDOS DE ADMINISTRAÇÃO
# ============================================================================

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Banir usuário permanentemente"""
    user_id = update.effective_user.id
    if user_id != DONO_ID and not get_adm_permissao(user_id, "todas"):
        await update.message.reply_text("⚠️ Acesso restrito ao dono ou ADMs com permissão total.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Uso: /ban <ID_USUARIO>")
        return
    
    try:
        alvo_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Use números inteiros.")
        return
    
    if alvo_id == DONO_ID:
        await update.message.reply_text("🚫 Você não pode banir o dono!")
        return
    
    if alvo_id == user_id:
        await update.message.reply_text("🤔 Você não pode se banir.")
        return
    
    user_data = get_user_data(alvo_id)
    user_data["ban"] = True
    salvar_dados()
    
    # Notificar usuário banido (se possível)
    try:
        await context.bot.send_message(
            chat_id=alvo_id,
            text="🚫 <b>Você foi banido permanentemente deste bot.</b>",
            parse_mode="HTML"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ Usuário <code>{alvo_id}</code> banido com sucesso!",
        parse_mode="HTML"
    )
    registrar_transacao("ban_usuario", {
        "adm_id": user_id,
        "adm_nome": adms.get(user_id, {}).get("nome", "Desconhecido"),
        "user_id": alvo_id,
        "user_nome": user_data.get("nome", "Desconhecido")
    })

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desbanir usuário"""
    user_id = update.effective_user.id
    if user_id != DONO_ID and not get_adm_permissao(user_id, "todas"):
        await update.message.reply_text("⚠️ Acesso restrito ao dono ou ADMs com permissão total.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Uso: /unban <ID_USUARIO>")
        return
    
    try:
        alvo_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Use números inteiros.")
        return
    
    user_data = get_user_data(alvo_id)
    user_data["ban"] = False
    salvar_dados()
    
    # Notificar usuário desbanido
    try:
        await context.bot.send_message(
            chat_id=alvo_id,
            text="✅ <b>Seu acesso foi restaurado!</b>",
            parse_mode="HTML"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ Usuário <code>{alvo_id}</code> desbanido com sucesso!",
        parse_mode="HTML"
    )
    registrar_transacao("unban_usuario", {
        "adm_id": user_id,
        "adm_nome": adms.get(user_id, {}).get("nome", "Desconhecido"),
        "user_id": alvo_id,
        "user_nome": user_data.get("nome", "Desconhecido")
    })

async def addsaldo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adicionar saldo manualmente a um usuário"""
    user_id = update.effective_user.id
    if user_id != DONO_ID and not get_adm_permissao(user_id, "todas"):
        await update.message.reply_text("⚠️ Acesso restrito ao dono ou ADMs com permissão total.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /addsaldo <ID_USUARIO> <VALOR>")
        return
    
    try:
        alvo_id = int(context.args[0])
        valor = float(context.args[1].replace(',', '.'))
        if valor <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Valor inválido. Use números positivos (ex: 50.00 ou 50,00)")
        return
    
    user_data = get_user_data(alvo_id)
    saldo_anterior = user_data["saldo"]
    user_data["saldo"] += valor
    salvar_dados()
    
    # Notificar usuário
    try:
        await context.bot.send_message(
            chat_id=alvo_id,
            text=(
                f"💰 <b>Saldo adicionado!</b>\n"
                f"Valor: {formatar_moeda(valor)}\n"
                f"Saldo anterior: {formatar_moeda(saldo_anterior)}\n"
                f"Saldo atual: {formatar_moeda(user_data['saldo'])}"
            ),
            parse_mode="HTML"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ Adicionado {formatar_moeda(valor)} ao usuário <code>{alvo_id}</code>!\n"
        f"Saldo atual: {formatar_moeda(user_data['saldo'])}",
        parse_mode="HTML"
    )
    registrar_transacao("addsaldo_manual", {
        "adm_id": user_id,
        "adm_nome": adms.get(user_id, {}).get("nome", "Desconhecido"),
        "user_id": alvo_id,
        "user_nome": user_data.get("nome", "Desconhecido"),
        "valor": valor,
        "saldo_anterior": saldo_anterior,
        "saldo_novo": user_data["saldo"]
    })

async def addprodutos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adicionar múltiplos produtos (cartões) ao estoque"""
    user_id = update.effective_user.id
    if user_id != DONO_ID and not get_adm_permissao(user_id, "todas"):
        await update.message.reply_text("⚠️ Acesso restrito ao dono ou ADMs com permissão total.")
        return
    
    # Pegar texto completo da mensagem (depois do comando)
    texto_completo = update.message.text.strip()
    if not texto_completo.startswith("/addprodutos"):
        await update.message.reply_text("❌ Formato inválido.")
        return
    
    # Extrair apenas os produtos (remover o comando)
    produtos_texto = texto_completo.replace("/addprodutos", "", 1).strip()
    
    if not produtos_texto:
        await update.message.reply_text(
            "📦 <b>ADICIONAR PRODUTOS</b>\n\n"
            "Envie os produtos no formato:\n"
            "<code>/addprodutos\n"
            "5529290480366572|06|2028|218\n"
            "4985550270884773|07|2030|134\n"
            "...</code>",
            parse_mode="HTML"
        )
        return
    
    # Processar cada linha
    linhas = produtos_texto.strip().split('\n')
    adicionados = 0
    invalidos = 0
    
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith('/'):
            continue
        
        # Validar formato mínimo (deve ter 3 pipes)
        if linha.count('|') < 3:
            invalidos += 1
            continue
        
        # Adicionar ao estoque
        numeros_disponiveis.append(linha)
        adicionados += 1
    
    salvar_dados()
    get_grupos.cache_clear()  # Limpar cache para atualizar grupos
    
    await update.message.reply_text(
        f"✅ <b>Produtos adicionados!</b>\n"
        f"📦 Adicionados: {adicionados}\n"
        f"❌ Inválidos: {invalidos}\n"
        f"📦 Total em estoque: {len(numeros_disponiveis)}",
        parse_mode="HTML"
    )
    registrar_transacao("addprodutos", {
        "adm_id": user_id,
        "adm_nome": adms.get(user_id, {}).get("nome", "Desconhecido"),
        "quantidade": adicionados,
        "invalidos": invalidos,
        "estoque_total": len(numeros_disponiveis)
    })

async def aviso_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar aviso broadcast para todos os usuários"""
    user_id = update.effective_user.id
    if user_id != DONO_ID and not get_adm_permissao(user_id, "todas"):
        await update.message.reply_text("⚠️ Acesso restrito ao dono ou ADMs com permissão total.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 <b>ENVIAR AVISO</b>\n\n"
            "Uso: <code>/aviso mensagem aqui</code>\n"
            "Ex: <code>/aviso Bonus de 50% na recarga só hoje!</code>",
            parse_mode="HTML"
        )
        return
    
    mensagem = " ".join(context.args)
    total_enviados = 0
    total_falhas = 0
    
    # Enviar para todos os usuários (exceto banidos)
    for uid, dados in usuarios.items():
        if dados.get("ban", False):
            continue
        
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "🔔 <b>AVISOOFFICIAL</b>\n"
                    "━━━━━━━━━━━━━━━━\n"
                    f"{mensagem}\n"
                    "━━━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML"
            )
            total_enviados += 1
            time.sleep(0.05)  # Evitar flood no Telegram
        except:
            total_falhas += 1
    
    await update.message.reply_text(
        f"✅ <b>Aviso enviado!</b>\n"
        f"📤 Enviados: {total_enviados}\n"
        f"❌ Falhas: {total_falhas}\n"
        f"👥 Total de usuários: {len(usuarios)}",
        parse_mode="HTML"
    )
    registrar_transacao("aviso_broadcast", {
        "adm_id": user_id,
        "adm_nome": adms.get(user_id, {}).get("nome", "Desconhecido"),
        "mensagem": mensagem,
        "enviados": total_enviados,
        "falhas": total_falhas
    })


# ============================================================================
# HANDLERS DE COMPRA E PERFIL DO USUÁRIO
# ============================================================================

async def comprar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    grupos = get_grupos()
    if not grupos:
        await query.edit_message_text("❌ <b>Estoque vazio no momento.</b>", parse_mode="HTML")
        return
    
    destaques = [p for p in config_sistema["bin_destaque"] if p in grupos and grupos[p]]
    normais = [p for p in grupos.keys() if p not in destaques and grupos[p]]
    
    botoes = []
    
    if destaques:
        linha = []
        for prefixo in destaques[:4]:
            contagem = len(grupos[prefixo])
            linha.append(InlineKeyboardButton(f"🔥 {nome_bin(prefixo)} ({contagem})", callback_data=f"bin_{prefixo}"))
        botoes.append(linha)
        botoes.append([InlineKeyboardButton("— Outras BINs —", callback_data="comprar_inicio")])
    
    todas_bins = destaques + normais
    for i in range(0 if not destaques else 4, len(todas_bins), 2):
        linha = []
        for j in range(2):
            if i + j < len(todas_bins):
                prefixo = todas_bins[i+j]
                if prefixo in grupos and grupos[prefixo]:
                    contagem = len(grupos[prefixo])
                    linha.append(InlineKeyboardButton(f"{nome_bin(prefixo)} ({contagem})", callback_data=f"bin_{prefixo}"))
        if linha:
            botoes.append(linha)
    
    botoes.append([InlineKeyboardButton("↩️ Voltar", callback_data="voltar_menu")])
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(
        "📦 <b>ESCOLHA UMA BIN PARA COMPRAR</b>\n\n⚠️ Sem reembolso após entrega.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def bin_escolhida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prefixo = query.data.replace("bin_", "")
    grupos = get_grupos()
    
    if prefixo not in grupos or not grupos[prefixo]:
        await query.edit_message_text("❌ <b>BIN esgotada.</b>", parse_mode="HTML")
        return
    
    amostra = grupos[prefixo][0]
    mascara = mascara_numero(amostra)
    contagem = len(grupos[prefixo])
    preco = preco_bin(prefixo)
    nome = nome_bin(prefixo)
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirmar Compra", callback_data=f"confirm_{prefixo}")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="comprar_inicio")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💳 <b>{nome}</b>\n\n"
        f"🔢 Exemplo: <code>{mascara}</code>\n"
        f"💰 Preço: {formatar_moeda(preco)}\n"
        f"📦 Disponíveis: {contagem}\n\n"
        f"⚠️ <i>Sem reembolso após entrega</i>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def confirmar_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if user_data["ban"]:
        await query.answer("🚫 Você está banido.", show_alert=True)
        return
    
    prefixo = query.data.replace("confirm_", "")
    preco = preco_bin(prefixo)
    
    if user_data["saldo"] < preco:
        await query.answer(f"⚠️ Saldo insuficiente! ({formatar_moeda(preco)} necessário)", show_alert=True)
        return
    
    if not verificar_limite_compras(user_id):
        await query.answer(f"⚠️ Limite de {config_sistema['limite_compras_hora']} compras/hora atingido!", show_alert=True)
        return
    
    grupos = get_grupos()
    if prefixo not in grupos or not grupos[prefixo]:
        await query.edit_message_text("❌ <b>BIN esgotada no momento.</b>", parse_mode="HTML")
        return
    
    numero = random.choice(grupos[prefixo])
    if not config_sistema["modo_teste"]:
        numeros_disponiveis.remove(numero)
    
    user_data["saldo"] -= preco
    user_data["compras"] += 1
    user_data["historico"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "numero": numero,
        "valor": preco
    })
    
    config_sistema["vendas_totais"] += 1
    
    vendas_log.append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "user_id": user_id,
        "user_nome": user_data["nome"],
        "numero": numero,
        "prefixo": prefixo,
        "valor": preco
    })
    
    # Creditar afiliado se existir
    if user_data.get("indicador_id"):
        indicador_id = user_data["indicador_id"]
        if indicador_id in usuarios:
            comissao = (preco * config_sistema["comissao_afiliado"]) / 100
            usuarios[indicador_id]["saldo_afiliado"] += comissao
            usuarios[indicador_id]["afiliados_validos"] += 1  # Tornar válido ao comprar
            try:
                await context.bot.send_message(
                    chat_id=indicador_id,
                    text=f"🎁 <b>Afiliado comprou!</b>\nVocê ganhou {formatar_moeda(comissao)} de comissão.",
                    parse_mode="HTML"
                )
            except:
                pass
    
    modo = " (MODO TESTE)" if config_sistema["modo_teste"] else ""
    await query.edit_message_text(
        f"✅ <b>COMPRA APROVADA{modo}</b>\n\n"
        f"💳 {nome_bin(prefixo)}\n"
        f"🔢 <code>{numero}</code>\n\n"
        f"💰 Saldo restante: {formatar_moeda(user_data['saldo'])}\n"
        f"📦 Suas compras: {user_data['compras']}",
        parse_mode="HTML"
    )
    
    get_grupos.cache_clear()
    salvar_dados()
    
    registrar_transacao("compra_realizada", {
        "user_id": user_id,
        "user_nome": user_data["nome"],
        "prefixo": prefixo,
        "numero_mascarado": mascara_numero(numero),
        "valor": preco
    })

async def menu_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    historico = user_data["historico"][-5:]
    hist_text = "\n".join([
        f"• {h['data']}: {nome_bin(h['numero'][:6])} ({formatar_moeda(h['valor'])})"
        for h in historico
    ]) if historico else "Nenhuma compra registrada."
    
    msg = (
        f"👤 <b>MINHA CONTA</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Nome: {user_data['nome']}\n"
        f"💰 Saldo: {formatar_moeda(user_data['saldo'])}\n"
        f"🛒 Compras: {user_data['compras']}\n"
    )
    
    if user_data.get("afiliado_aprovado"):
        msg += f"👥 Afiliados Válidos: {user_data.get('afiliados_validos', 0)}\n"
        msg += f"🤑 Saldo Afiliado: {formatar_moeda(user_data.get('saldo_afiliado', 0.0))}\n"
    
    msg += f"\n📜 <b>Últimas compras:</b>\n{hist_text}"
    
    botoes = [
        [InlineKeyboardButton("💵 Recarregar Saldo", callback_data="recarga_info")],
    ]
    
    if user_data.get("afiliado_aprovado"):
        botoes.append([InlineKeyboardButton("🤝 Meu Link de Afiliado", callback_data="menu_afiliados")])
    else:
        botoes.append([InlineKeyboardButton("🤝 Quero ser Afiliado", callback_data="solicitar_afiliado")])
    
    botoes.append([InlineKeyboardButton("↩️ Voltar", callback_data="voltar_menu")])
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def recarga_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    msg = (
        f"💰 <b>RECARGA DE SALDO</b>\n\n"
        f"⚠️ Valor mínimo: R$ 20,00\n\n"
        f"📱 Para recarregar:\n"
        f"1. Clique no botão abaixo\n"
        f"2. Digite o valor desejado\n"
        f"3. Aguarde um ADM aceitar sua solicitação\n"
        f"4. Receba a chave PIX e pague\n"
        f"5. ADM confirma e seu saldo é creditado"
    )
    
    botoes = [
        [InlineKeyboardButton("➕ Solicitar Recarga", callback_data="solicitar_recarga")],
        [InlineKeyboardButton("↩️ Voltar", callback_data="menu_perfil")]
    ]
    reply_markup = InlineKeyboardMarkup(botoes)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)

async def solicitar_recarga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["aguardando_valor_recarga"] = True
    
    await query.edit_message_text(
        "💰 <b>SOLICITAR RECARGA</b>\n\n"
        "Digite o valor desejado (mínimo R$ 20,00):",
        parse_mode="HTML"
    )

async def receber_valor_recarga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get("aguardando_valor_recarga"):
        return
    
    try:
        valor = float(update.message.text.strip().replace(',', '.'))
        if valor < 20.00:
            await update.message.reply_text("⚠️ Valor mínimo é R$ 20,00")
            return
    except:
        await update.message.reply_text("❌ Valor inválido. Envie um número.")
        return
    
    context.user_data.pop("aguardando_valor_recarga", None)
    
    # Criar requisição
    req_id = f"REQ_{int(time.time())}"
    requisicoes_recarga[req_id] = {
        "id": req_id,
        "user_id": user_id,
        "user_nome": update.effective_user.full_name,
        "valor": valor,
        "status": "aguardando_adm",
        "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "adm_responsavel": None
    }
    salvar_dados()
    
    # Notificar ADMs
    notificacao = (
        f"📥 <b>NOVA REQUISIÇÃO DE RECARGA</b>\n\n"
        f"ID: {req_id}\n"
        f"Usuário: {update.effective_user.full_name} (ID: {user_id})\n"
        f"Valor: {formatar_moeda(valor)}\n"
        f"Tempo restante: 1:00\n\n"
        f"[ ✅ Aceitar ] [ ❌ Recusar ]"
    )
    
    teclado_adm = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceitar", callback_data=f"aceitar_req_{req_id}")],
        [InlineKeyboardButton("❌ Recusar", callback_data=f"recusar_req_{req_id}")]
    ])
    
    notificados = 0
    for adm_id, adm in adms.items():
        if adm["status"] == "online" and get_adm_permissao(adm_id, "aceitar_recarga"):
            try:
                await context.bot.send_message(
                    chat_id=adm_id,
                    text=notificacao,
                    reply_markup=teclado_adm,
                    parse_mode="HTML"
                )
                notificados += 1
            except:
                pass
    
    if notificados == 0:
        await update.message.reply_text(
            "⚠️ <b>Nenhum ADM online no momento.</b>\nTente novamente mais tarde.",
            parse_mode="HTML"
        )
        del requisicoes_recarga[req_id]
        salvar_dados()
        return
    
    await update.message.reply_text(
        f"✅ <b>Requisição enviada!</b>\n\n"
        f"ID: {req_id}\n"
        f"Valor: {formatar_moeda(valor)}\n\n"
        f"Aguarde um ADM aceitar sua solicitação (1 minuto).\n"
        f"Você será notificado quando um ADM aceitar.",
        parse_mode="HTML"
    )
    
    registrar_transacao("recarga_solicitada", {
        "req_id": req_id,
        "user_id": user_id,
        "user_nome": update.effective_user.full_name,
        "valor": valor
    })

async def voltar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
# ============================================================================
# INICIALIZAÇÃO
# ============================================================================
def main():
    carregar_dados()
    
    application = Application.builder().token(TOKEN).build()
    
    # Handlers principais
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cobrar", cobrar_cmd))
    application.add_handler(CommandHandler("pago", pago_cmd))
   
    # Comandos de administração (com o /aviso adicionado)
    application.add_handler(CommandHandler("ban", ban_cmd))
    application.add_handler(CommandHandler("unban", unban_cmd))
    application.add_handler(CommandHandler("addsaldo", addsaldo_cmd)) 
    application.add_handler(CommandHandler("addprodutos", addprodutos_cmd))
    application.add_handler(CommandHandler("aviso", aviso_cmd))  # <-- FALTAVA ESTE
    
    # Callbacks principais
    application.add_handler(CallbackQueryHandler(start, pattern="^voltar_menu$"))
    application.add_handler(CallbackQueryHandler(comprar_inicio, pattern="^comprar_inicio$"))
    application.add_handler(CallbackQueryHandler(bin_escolhida, pattern=r"^bin_"))
    application.add_handler(CallbackQueryHandler(confirmar_compra, pattern=r"^confirm_"))
    application.add_handler(CallbackQueryHandler(menu_perfil, pattern="^menu_perfil$"))
    application.add_handler(CallbackQueryHandler(recarga_info, pattern="^recarga_info$"))
    application.add_handler(CallbackQueryHandler(solicitar_recarga, pattern="^solicitar_recarga$"))
    application.add_handler(CallbackQueryHandler(solicitar_afiliado, pattern="^solicitar_afiliado$"))
    application.add_handler(CallbackQueryHandler(menu_afiliados, pattern="^menu_afiliados$"))
    application.add_handler(CallbackQueryHandler(converter_saldo_afiliado, pattern="^converter_saldo_afiliado$"))
    application.add_handler(CallbackQueryHandler(vender_afiliados_validos, pattern="^vender_afiliados_validos$"))
    application.add_handler(CallbackQueryHandler(confirmar_venda_afiliados, pattern=r"^confirmar_venda_afiliados_"))
    application.add_handler(CallbackQueryHandler(painel_adm, pattern="^painel_adm$"))
    application.add_handler(CallbackQueryHandler(ver_requisicoes, pattern="^ver_requisicoes$"))
    application.add_handler(CallbackQueryHandler(aceitar_requisicao, pattern=r"^aceitar_req_"))
    application.add_handler(CallbackQueryHandler(recusar_requisicao, pattern=r"^recusar_req_"))
    application.add_handler(CallbackQueryHandler(controle_total, pattern="^controle_total$"))
    application.add_handler(CallbackQueryHandler(gerenciar_adms, pattern="^gerenciar_adms$"))
    application.add_handler(CallbackQueryHandler(adicionar_adm, pattern="^adicionar_adm$"))
    application.add_handler(CallbackQueryHandler(editar_interface, pattern="^editar_interface$"))
    application.add_handler(CallbackQueryHandler(estatisticas_menu, pattern="^estatisticas_menu$"))
    application.add_handler(CallbackQueryHandler(alterar_periodo, pattern="^alterar_periodo$"))
    application.add_handler(CallbackQueryHandler(definir_periodo, pattern=r"^periodo_"))
    
    # Handlers de texto
    application.add_handler(MessageHandler(
        filters.TEXT & filters.User(user_id=DONO_ID) & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        receber_id_adm
    ), group=1)
    
    application.add_handler(MessageHandler(
        filters.TEXT & filters.User(user_id=DONO_ID) & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        receber_edicao_interface
    ), group=2)
    
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        receber_valor_recarga
    ), group=3)
    
    logger.info("Bot iniciado com sucesso!")
    application.run_polling()

if __name__ == '__main__':
    main()
