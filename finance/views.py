"""
Views do app finance.

Localização: finance/views.py

Views do módulo finance. Elas chamam services para executar
a lógica de negócio e retornam respostas.
"""
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
import logging
import os
import json
from finance.services.transaction_service import TransactionService
from finance.services.dashboard_service import DashboardService
from finance.services.compromisso_service import CompromissoService
from core.services.categoria_usuario_service import CategoriaUsuarioService
from finance.models.categoria_model import CategoriaModel
from core.decorators import audit_log
from core.decorators.auth import login_required_mongo
from datetime import datetime, timedelta
from dotenv import load_dotenv,find_dotenv
load_dotenv(find_dotenv())


logger = logging.getLogger(__name__)


def index_view(request):
    """View principal do finance."""
    return JsonResponse({
        'message': 'Finance API',
        'status': 'ok'
    })


@login_required_mongo
def dashboard_view(request):
    """
    View do dashboard financeiro (HTML).
    
    Requer autenticação via sessão.
    """
    return render(request, 'finance/dashboard.html', {
        'user': request.user_mongo if hasattr(request, 'user_mongo') and request.user_mongo else None
    })


def dashboard_api_view(request):
    """
    API endpoint para dados do dashboard.
    
    GET /api/finance/dashboard/?period=mensal
    
    SEGURANÇA: user_id é extraído do request.user_mongo (garantido pelo middleware).
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    # SEGURANÇA: user_id vem do middleware, não do request do cliente
    user_id = str(request.user_mongo['_id'])
    period = request.GET.get('period', 'mensal')
    
    service = DashboardService()
    data = service.get_dashboard_data(
        user_id=user_id,  # Sempre do usuário autenticado
        period=period
    )
    
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False})


def insights_api_view(request):
    """
    API endpoint para insights financeiros gerados por IA.

    GET /finance/api/insights/?period=mensal

    Reaproveita a lógica do dashboard para obter dados consolidados,
    envia para OpenAI (gpt-4o-mini) e retorna insight, alerta e recomendação em JSON.
    SEGURANÇA: user_id é extraído do request.user_mongo (garantido pelo middleware).
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)

    user_id = str(request.user_mongo['_id'])
    period = request.GET.get('period', 'mensal')

    try:
        service = DashboardService()
        dashboard_data = service.get_dashboard_data(user_id=user_id, period=period)
    except Exception as e:
        logger.exception("Erro ao obter dados do dashboard para insights: %s", e)
        return JsonResponse({
            'error': 'Erro ao carregar dados',
            'message': str(e)
        }, status=500)

    # Extrair apenas dados consolidados para o prompt (valores serializáveis para JSON)
    def _serialize(obj):
        if obj is None:
            return None
        if isinstance(obj, (int, float, str, bool)):
            return obj
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_serialize(v) for v in obj]
        return str(obj)

    raw = {
        'total_income': dashboard_data.get('total_income', 0),
        'total_expenses': dashboard_data.get('total_expenses', 0),
        'balance': dashboard_data.get('balance', 0),
        'day_with_highest_expense': dashboard_data.get('day_with_highest_expense'),
        'category_with_highest_expense': dashboard_data.get('category_with_highest_expense'),
        'hour_with_highest_expense': dashboard_data.get('hour_with_highest_expense'),
    }
    payload = _serialize(raw)
    dados_json = json.dumps(payload, ensure_ascii=False, indent=2)

    prompt = (
        "Você é um assistente financeiro inteligente.\n"
        "Analise os dados abaixo e gere:\n\n"
        "- Um insight estratégico\n"
        "- Um alerta (se houver risco)\n"
        "- Uma recomendação prática\n\n"
        "Responda em JSON no formato:\n"
        '{"insight": "...", "alerta": "...", "recomendacao": "..."}\n\n'
        "Dados:\n"
        f"{dados_json}"
    )
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.warning("OPENAI_API_KEY não configurada; retornando fallback para insights.")
        fallback = {
            'insight': 'Configure OPENAI_API_KEY no .env para receber análises automáticas.',
            'alerta': '',
            'recomendacao': 'Adicione OPENAI_API_KEY nas variáveis de ambiente e chame o endpoint novamente.',
        }
        return JsonResponse(fallback, json_dumps_params={'ensure_ascii': False})

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.5,
        )
        content = (response.choices[0].message.content or '').strip()
    except Exception as e:
        logger.exception("Erro ao chamar OpenAI para insights: %s", e)
        fallback = {
            'insight': 'Não foi possível gerar o insight no momento. Tente novamente mais tarde.',
            'alerta': '',
            'recomendacao': 'Verifique sua conexão e a configuração da OPENAI_API_KEY.',
        }
        return JsonResponse(fallback, json_dumps_params={'ensure_ascii': False})

    # Parse da resposta como JSON
    try:
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:].strip()
        parsed = json.loads(content)
        result = {
            'insight': parsed.get('insight', ''),
            'alerta': parsed.get('alerta', ''),
            'recomendacao': parsed.get('recomendacao', ''),
        }
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Resposta da OpenAI não é JSON válido: %s", e)
        result = {
            'insight': 'Análise gerada com sucesso, mas o formato não pôde ser processado.',
            'alerta': '',
            'recomendacao': 'Tente novamente ou altere o período para obter um novo insight.',
        }

    return JsonResponse(result, json_dumps_params={'ensure_ascii': False})


@login_required_mongo
def charts_api_view(request):
    """
    API endpoint para dados de gráficos.
    
    GET /api/finance/charts/?type=all&period=mensal
    
    SEGURANÇA: user_id é extraído do request.user_mongo (garantido pelo middleware).
    """
    # Verificação adicional de segurança
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({
            'error': 'Não autenticado',
            'message': 'É necessário fazer login para acessar os gráficos'
        }, status=401)
    
    # SEGURANÇA: user_id vem do middleware, não do request do cliente
    user_id = str(request.user_mongo['_id'])
    period = request.GET.get('period', 'mensal')
    chart_type = request.GET.get('type', 'all')
    
    try:
        service = DashboardService()
        
        if chart_type == 'category':
            data = service.get_expenses_by_category_chart_data(user_id, period)
        elif chart_type == 'weekday':
            data = service.get_expenses_by_weekday_chart_data(user_id, period)
        elif chart_type == 'hour':
            data = service.get_expenses_by_hour_chart_data(user_id, period)
        else:  # 'all'
            data = service.get_all_charts_data(user_id, period)
        
        return JsonResponse(data, json_dumps_params={'ensure_ascii': False})
    
    except ValueError as e:
        return JsonResponse({
            'error': 'Erro ao buscar dados dos gráficos',
            'message': str(e)
        }, status=400)
    except Exception as e:
        import traceback
        return JsonResponse({
            'error': 'Erro interno do servidor',
            'message': str(e),
            'traceback': traceback.format_exc() if request.GET.get('debug') == 'true' else None
        }, status=500)


def transactions_api_view(request):
    """
    API endpoint para lista de transações com paginação.
    
    GET /finance/api/transactions/?period=mensal&page=1&limit=20
    
    SEGURANÇA: user_id é extraído do request.user_mongo (garantido pelo middleware).
    Nenhum usuário pode acessar transações de outro usuário.
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    # SEGURANÇA: user_id vem do middleware, não do request do cliente
    user_id = str(request.user_mongo['_id'])
    period = request.GET.get('period', 'mensal')
    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 20))
    
    # Validações
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    skip = (page - 1) * limit
    
    service = DashboardService()
    start_date, end_date = service._get_period_dates(period)
    
    # SEGURANÇA: user_id sempre do usuário autenticado
    data = service._get_filtered_transactions(
        user_id=user_id,  # Sempre do usuário autenticado
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        skip=skip
    )
    
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False})


def report_api_view(request):
    """
    API endpoint para geração de relatórios.
    
    GET /finance/api/report/?period=mensal&format=text&use_ai=false
    
    SEGURANÇA: user_id é extraído do request.user_mongo (garantido pelo middleware).
    Relatórios sempre gerados apenas com dados do usuário autenticado.
    
    Parâmetros:
    - period: 'diário', 'semanal', 'mensal'
    - format: 'text', 'json' (futuro: 'pdf')
    - use_ai: 'true' ou 'false' (futuro: análise com IA)
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    # SEGURANÇA: user_id vem do middleware, não do request do cliente
    user_id = str(request.user_mongo['_id'])
    period = request.GET.get('period', 'mensal')
    format_type = request.GET.get('format', 'text')
    use_ai = request.GET.get('use_ai', 'false').lower() == 'true'
    
    # Validações
    valid_periods = ['diário', 'semanal', 'mensal']
    if period not in valid_periods:
        period = 'mensal'
    
    valid_formats = ['text', 'json', 'pdf']
    if format_type not in valid_formats:
        format_type = 'text'
    
    from finance.services.report_service import ReportService
    report_service = ReportService()
    
    try:
        if format_type == 'pdf':
            # Por enquanto, retorna erro (não implementado)
            return JsonResponse({
                'error': 'Geração de PDF ainda não implementada',
                'available_formats': ['text', 'json']
            }, status=501)
        
        # SEGURANÇA: user_id sempre do usuário autenticado
        report = report_service.generate_report(
            user_id=user_id,  # Sempre do usuário autenticado
            period=period,
            format=format_type,
            use_ai=use_ai
        )
        
        return JsonResponse(report, json_dumps_params={'ensure_ascii': False})
    
    except Exception as e:
        return JsonResponse({
            'error': 'Erro ao gerar relatório',
            'message': str(e)
        }, status=500)


def report_view(request):
    """
    View HTML para exibir relatório em página simples.
    
    GET /finance/report/?period=mensal
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        from django.shortcuts import redirect
        return redirect('core:login')
    
    period = request.GET.get('period', 'mensal')
    
    from finance.services.report_service import ReportService
    report_service = ReportService()
    
    try:
        report_data = report_service.generate_text_report(
            user_id=str(request.user_mongo['_id']),
            period=period
        )
        
        return render(request, 'finance/report.html', {
            'user': request.user_mongo,
            'report_text': report_data['report_text'],
            'metadata': report_data['metadata'],
            'summary': report_data['summary']
        })
    
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Erro ao gerar relatório: {str(e)}')
        from django.shortcuts import redirect
        return redirect('finance:dashboard')


@login_required_mongo
def categorias_view(request):
    """
    View para gerenciar categorias personalizadas.
    
    GET: Exibe lista de categorias e formulário para adicionar
    POST: Cria nova categoria
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return redirect('/login/')
    
    user_id = str(request.user_mongo['_id'])
    categoria_service = CategoriaUsuarioService()
    
    if request.method == 'POST':
        action = request.POST.get('action', 'add')
        
        if action == 'add':
            nome = request.POST.get('nome', '').strip()
            tipo = request.POST.get('tipo', '').strip()
            
            try:
                categoria_service.adicionar_categoria(user_id, tipo, nome)
                messages.success(request, f'Categoria "{nome}" adicionada com sucesso!')
            except ValueError as e:
                messages.error(request, str(e))
        
        elif action == 'remove':
            nome = request.POST.get('nome', '').strip()
            tipo = request.POST.get('tipo', '').strip()
            
            try:
                categoria_service.remover_categoria(user_id, tipo, nome)
                messages.success(request, f'Categoria "{nome}" removida com sucesso!')
            except ValueError as e:
                messages.error(request, str(e))
        
        elif action == 'edit':
            nome_antigo = request.POST.get('nome_antigo', '').strip()
            nome_novo = request.POST.get('nome_novo', '').strip()
            tipo = request.POST.get('tipo', '').strip()
            
            try:
                categoria_service.editar_categoria(user_id, tipo, nome_antigo, nome_novo)
                messages.success(request, f'Categoria atualizada com sucesso!')
            except ValueError as e:
                messages.error(request, str(e))
        
        return redirect('finance:categorias')
    
    # Busca categorias do usuário
    categorias_por_tipo = categoria_service.get_categorias_usuario(user_id)
    tipos_disponiveis = CategoriaModel.TIPOS
    
    return render(request, 'finance/categorias.html', {
        'user': request.user_mongo,
        'categorias_por_tipo': categorias_por_tipo,
        'tipos_disponiveis': tipos_disponiveis
    })




@login_required_mongo
def categorias_api_view(request):
    """
    API endpoint para buscar categorias do usuário.
    
    GET /finance/api/categorias/?tipo=receita
    
    SEGURANÇA: Requer autenticação via sessão. Apenas usuários autenticados
    podem acessar suas próprias categorias.
    """
    # Verificação adicional de segurança
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({
            'error': 'Não autenticado',
            'message': 'É necessário fazer login para acessar as categorias'
        }, status=401)
    
    # Obtém o ID do usuário autenticado (garantido pelo middleware e decorator)
    user_id = str(request.user_mongo['_id'])
    tipo = request.GET.get('tipo', None)
    
    try:
        categoria_service = CategoriaUsuarioService()
        
        if tipo:
            # Retorna apenas categorias do tipo especificado
            categorias = categoria_service.get_categorias_por_tipo(user_id, tipo)
            categorias_formatted = [{'nome': nome, 'tipo': tipo} for nome in categorias]
        else:
            # Retorna todas as categorias formatadas
            categorias_formatted = categoria_service.get_todas_categorias_formatadas(user_id)
        
        return JsonResponse({
            'categorias': categorias_formatted,
            'user_id': user_id  # Para debug (pode remover em produção)
        }, json_dumps_params={'ensure_ascii': False})
    
    except ValueError as e:
        return JsonResponse({
            'error': 'Erro ao buscar categorias',
            'message': str(e)
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Erro interno do servidor',
            'message': str(e)
        }, status=500)

from .services.ai_insights import gerar_insights_financeiros


@login_required_mongo
def api_insights(request):
    period = request.GET.get("period", "mensal")

    # 🔹 DADOS TEMPORÁRIOS PARA TESTE
    # Depois vamos integrar com os dados reais do dashboard
    dados_para_ia = {
        "periodo": period,
        "total_income": 10000,
        "total_expenses": 7500,
        "balance": 2500,
        "top_category": "Transporte",
        "top_day": "Segunda",
        "top_hour": "18:00",
    }

    insights = gerar_insights_financeiros(dados_para_ia)

    return JsonResponse(insights)

@login_required_mongo
def criar_transacao_view(request):
    """
    View para criar nova transação.
    
    GET: Exibe formulário
    POST: Cria transação
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return redirect('/login/')
    
    user_id = str(request.user_mongo['_id'])
    categoria_service = CategoriaUsuarioService()
    
    # Busca todas as categorias do usuário para o formulário
    todas_categorias = categoria_service.get_todas_categorias_formatadas(user_id)
    
    return render(request, 'finance/criar_transacao.html', {
        'user': request.user_mongo,
        'categorias': todas_categorias
    })


def create_transaction_api_view(request):
    """
    API endpoint para criar transação.
    
    POST /finance/api/transactions/create/
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    user_id = str(request.user_mongo['_id'])
    
    try:
        import json
        from datetime import datetime
        
        # Tenta ler JSON primeiro, depois FormData
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = json.loads(request.body)
                transaction_type = data.get('tipo')
                categoria = data.get('categoria')
                valor = data.get('valor')
                descricao = data.get('descricao')
                data_str = data.get('data')  # Pode ser 'YYYY-MM-DD' ou 'YYYY-MM-DDTHH:MM:SS'
            except:
                transaction_type = None
                categoria = None
                valor = None
                descricao = None
                data_str = None
        else:
            transaction_type = request.POST.get('tipo')
            categoria = request.POST.get('categoria')
            valor = request.POST.get('valor')
            descricao = request.POST.get('descricao')
            data_str = request.POST.get('data')
        
        if not all([transaction_type, categoria, valor, descricao]):
            return JsonResponse({'error': 'Campos obrigatórios: tipo, categoria, valor, descricao'}, status=400)
        
        # Valida categoria do usuário
        categoria_service = CategoriaUsuarioService()
        categorias_usuario = categoria_service.get_categorias_usuario(user_id)
        
        # Verifica se categoria existe nas categorias do usuário
        categoria_valida = False
        for tipo_cat, nomes in categorias_usuario.items():
            if categoria in nomes:
                categoria_valida = True
                break
        
        if not categoria_valida:
            return JsonResponse({'error': 'Categoria inválida ou não pertence ao usuário'}, status=400)
        
        # Cria transação
        transaction_service = TransactionService()
        
        # Converte data_str para datetime se fornecido
        # Aceita formatos: 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS', 'YYYY-MM-DDTHH:MM'
        created_at = None
        if data_str:
            try:
                # Tenta formato ISO completo primeiro
                if 'T' in data_str:
                    if len(data_str) == 16:  # 'YYYY-MM-DDTHH:MM'
                        created_at = datetime.strptime(data_str, '%Y-%m-%dT%H:%M')
                    else:  # 'YYYY-MM-DDTHH:MM:SS' ou 'YYYY-MM-DDTHH:MM:SSZ'
                        created_at = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
                else:
                    # Apenas data, usa hora atual
                    created_at = datetime.strptime(data_str, '%Y-%m-%d')
            except Exception as e:
                # Se falhar, usa data/hora atual
                created_at = None
        
        transaction = transaction_service.create_transaction(
            user_id=user_id,
            amount=float(valor),
            description=descricao,
            transaction_type=transaction_type,
            category=categoria,
            created_at=created_at
        )
        
        return JsonResponse({
            'success': True,
            'transaction': {
                'id': str(transaction['_id']),
                'type': transaction['type'],
                'category': transaction['category'],
                'description': transaction['description'],
                'value': transaction['value']
            }
        }, json_dumps_params={'ensure_ascii': False})
    
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Erro ao criar transação: {str(e)}'}, status=500)


# ========================================
# AGENDA / COMPROMISSOS
# ========================================

@login_required_mongo
def agenda_view(request):
    """
    View da página de agenda.
    
    Requer autenticação via sessão.
    """
    return render(request, 'finance/agenda.html', {
        'user': request.user_mongo if hasattr(request, 'user_mongo') and request.user_mongo else None
    })


def agenda_api_view(request):
    """
    API endpoint para listar compromissos (formato FullCalendar).
    
    GET /finance/api/agenda/?start=2026-01-01&end=2026-01-31
    
    SEGURANÇA: user_id é extraído do request.user_mongo (garantido pelo middleware).
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    try:
        user_id = str(request.user_mongo['_id'])
        logger.info(f"[AGENDA_API] Buscando compromissos para user_id: {user_id}")
        
        # Obter parâmetros de data do FullCalendar
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        
        logger.info(f"[AGENDA_API] Parâmetros recebidos - start: {start_str}, end: {end_str}")
        
        # Valores padrão
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (datetime.utcnow() + timedelta(days=30)).replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Função auxiliar para parse de datas com múltiplos formatos
        def parse_date(date_str):
            """Parse de data com suporte a múltiplos formatos."""
            if not date_str:
                return None
            
            # Remover espaços
            date_str = date_str.strip()
            
            # Normalizar fuso horário: converter +HH:MM para +HHMM (formato Python strptime)
            # Python strptime requer +HHMM ou -HHMM, não +HH:MM
            import re
            # Padrão: -03:00 ou +03:00 -> -0300 ou +0300
            date_str = re.sub(r'([+-])(\d{2}):(\d{2})$', r'\1\2\3', date_str)
            
            # Lista de formatos a tentar (ordem importa - mais específicos primeiro)
            formats = [
                '%Y-%m-%dT%H:%M:%S.%f%z',  # Com microsegundos e fuso: 2026-01-13T00:00:00.000-0300
                '%Y-%m-%dT%H:%M:%S%z',  # Com fuso horário: 2026-01-13T00:00:00-0300
                '%Y-%m-%dT%H:%M:%S',  # Sem fuso: 2026-01-13T00:00:00
                '%Y-%m-%dT%H:%M',  # Sem segundos: 2026-01-13T00:00
                '%Y-%m-%d',  # Apenas data: 2026-01-13
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    # Se tem fuso horário, converter para UTC e remover timezone
                    if dt.tzinfo is not None:
                        # Converter para UTC e depois remover timezone info
                        from datetime import timezone
                        dt_utc = dt.astimezone(timezone.utc)  # Converte para UTC
                        dt = dt_utc.replace(tzinfo=None)  # Remove timezone info (naive UTC)
                    # Se não tem fuso horário, manter como está (assumir UTC)
                    logger.info(f"[AGENDA_API] Data parseada com sucesso: {date_str} -> {dt} (formato: {fmt})")
                    return dt
                except ValueError:
                    continue
                except Exception as e:
                    logger.warning(f"[AGENDA_API] Erro ao tentar formato {fmt}: {e}")
                    continue
            
            # Tentar com dateutil como fallback (mais flexível)
            try:
                from dateutil import parser
                from datetime import timezone
                dt = parser.parse(date_str)
                # Se tem timezone, converter para UTC e remover
                if dt.tzinfo is not None:
                    dt_utc = dt.astimezone(timezone.utc)
                    dt = dt_utc.replace(tzinfo=None)
                logger.info(f"[AGENDA_API] Data parseada com dateutil: {date_str} -> {dt}")
                return dt
            except Exception as e:
                logger.error(f"[AGENDA_API] Erro ao fazer parse da data {date_str}: {e}")
                raise ValueError(f"Formato de data inválido: {date_str}")
        
        # Parse das datas
        if start_str:
            try:
                start_date = parse_date(start_str)
                if start_date:
                    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            except Exception as e:
                logger.error(f"[AGENDA_API] Erro ao parsear start_date: {e}")
                return JsonResponse({
                    'error': 'Formato de data inicial inválido',
                    'message': str(e),
                    'received': start_str
                }, status=400)
        
        if end_str:
            try:
                end_date = parse_date(end_str)
                if end_date:
                    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            except Exception as e:
                logger.error(f"[AGENDA_API] Erro ao parsear end_date: {e}")
                return JsonResponse({
                    'error': 'Formato de data final inválido',
                    'message': str(e),
                    'received': end_str
                }, status=400)
        
        logger.info(f"[AGENDA_API] Buscando compromissos de {start_date} até {end_date}")
        
        # Buscar compromissos
        try:
            service = CompromissoService()
            compromissos = service.listar_compromissos(user_id, start_date, end_date)
            logger.info(f"[AGENDA_API] {len(compromissos)} compromissos encontrados")
            
            # Formatar para FullCalendar
            eventos = service.formatar_para_calendario(compromissos)
            logger.info(f"[AGENDA_API] {len(eventos)} eventos formatados")
            
            return JsonResponse(eventos, safe=False, json_dumps_params={'ensure_ascii': False})
            
        except Exception as e:
            logger.error(f"[AGENDA_API] Erro ao buscar compromissos: {e}", exc_info=True)
            return JsonResponse({
                'error': 'Erro ao buscar compromissos no banco de dados',
                'message': str(e)
            }, status=500)
        
    except Exception as e:
        logger.error(f"[AGENDA_API] Erro geral: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Erro ao processar requisição',
            'message': str(e)
        }, status=500)


def criar_compromisso_api_view(request):
    """
    API endpoint para criar compromisso.
    
    POST /finance/api/compromissos/create/
    
    Body JSON:
    {
        "titulo": "Reunião",
        "descricao": "Reunião com equipe",
        "data": "2026-01-15",
        "hora": "14:00",
        "tipo": "Reunião"
    }
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        user_id = str(request.user_mongo['_id'])
        import json
        data = json.loads(request.body)
        
        titulo = data.get('titulo', '').strip()
        descricao = data.get('descricao', '').strip()
        data_compromisso = data.get('data', '').strip()
        hora = data.get('hora', '').strip()
        hora_fim = data.get('hora_fim', '').strip()
        tipo = data.get('tipo', '').strip()
        
        if not titulo:
            return JsonResponse({'error': 'Título é obrigatório'}, status=400)
        
        if not data_compromisso:
            return JsonResponse({'error': 'Data é obrigatória'}, status=400)
        
        if not hora:
            return JsonResponse({'error': 'Horário de início é obrigatório'}, status=400)
        
        if not hora_fim:
            return JsonResponse({'error': 'Horário de término é obrigatório'}, status=400)
        
        # Validar que hora_fim é posterior a hora
        try:
            hora_parts = hora.split(':')
            hora_fim_parts = hora_fim.split(':')
            hora_minutos = int(hora_parts[0]) * 60 + int(hora_parts[1])
            hora_fim_minutos = int(hora_fim_parts[0]) * 60 + int(hora_fim_parts[1])
            
            if hora_fim_minutos <= hora_minutos:
                return JsonResponse({'error': 'O horário de término deve ser posterior ao horário de início'}, status=400)
        except:
            return JsonResponse({'error': 'Formato de horário inválido'}, status=400)
        
        service = CompromissoService()
        compromisso = service.criar_compromisso(
            user_id=user_id,
            titulo=titulo,
            descricao=descricao,
            data=data_compromisso,
            hora=hora,
            hora_fim=hora_fim,
            tipo=tipo if tipo else None
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Compromisso criado com sucesso!',
            'compromisso': {
                'id': str(compromisso.get('_id')),
                'titulo': compromisso.get('titulo'),
                'descricao': compromisso.get('descricao'),
                'data': compromisso.get('data').isoformat() if isinstance(compromisso.get('data'), datetime) else compromisso.get('data'),
                'hora': compromisso.get('hora'),
                'hora_inicio': compromisso.get('hora_inicio') or compromisso.get('hora'),
                'hora_fim': compromisso.get('hora_fim'),
                'tipo': compromisso.get('tipo'),
                'status': compromisso.get('status')
            }
        }, json_dumps_params={'ensure_ascii': False})
        
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Erro ao criar compromisso',
            'message': str(e)
        }, status=500)


def atualizar_compromisso_api_view(request, compromisso_id):
    """
    API endpoint para atualizar compromisso.
    
    PUT /finance/api/compromissos/<id>/update/
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    if request.method not in ['PUT', 'PATCH']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        user_id = str(request.user_mongo['_id'])
        import json
        data = json.loads(request.body)
        
        hora_fim = data.get('hora_fim', '').strip()
        
        # Validar hora_fim se fornecido
        if hora_fim and data.get('hora'):
            try:
                hora = data.get('hora', '').strip()
                hora_parts = hora.split(':')
                hora_fim_parts = hora_fim.split(':')
                hora_minutos = int(hora_parts[0]) * 60 + int(hora_parts[1])
                hora_fim_minutos = int(hora_fim_parts[0]) * 60 + int(hora_fim_parts[1])
                
                if hora_fim_minutos <= hora_minutos:
                    return JsonResponse({'error': 'O horário de término deve ser posterior ao horário de início'}, status=400)
            except:
                return JsonResponse({'error': 'Formato de horário inválido'}, status=400)
        
        service = CompromissoService()
        compromisso = service.atualizar_compromisso(
            compromisso_id=compromisso_id,
            user_id=user_id,
            titulo=data.get('titulo'),
            descricao=data.get('descricao'),
            data=data.get('data'),
            hora=data.get('hora'),
            hora_fim=hora_fim if hora_fim else None,
            tipo=data.get('tipo'),
            status=data.get('status')
        )
        
        if not compromisso:
            return JsonResponse({'error': 'Compromisso não encontrado'}, status=404)
        
        return JsonResponse({
            'success': True,
            'message': 'Compromisso atualizado com sucesso!',
            'compromisso': {
                'id': str(compromisso.get('_id')),
                'titulo': compromisso.get('titulo'),
                'descricao': compromisso.get('descricao'),
                'data': compromisso.get('data').isoformat() if isinstance(compromisso.get('data'), datetime) else compromisso.get('data'),
                'hora': compromisso.get('hora'),
                'hora_inicio': compromisso.get('hora_inicio') or compromisso.get('hora'),
                'hora_fim': compromisso.get('hora_fim'),
                'tipo': compromisso.get('tipo'),
                'status': compromisso.get('status')
            }
        }, json_dumps_params={'ensure_ascii': False})
        
    except PermissionError as e:
        return JsonResponse({'error': str(e)}, status=403)
    except Exception as e:
        return JsonResponse({
            'error': 'Erro ao atualizar compromisso',
            'message': str(e)
        }, status=500)


def excluir_compromisso_api_view(request, compromisso_id):
    """
    API endpoint para excluir compromisso.
    
    DELETE /finance/api/compromissos/<id>/delete/
    """
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        user_id = str(request.user_mongo['_id'])
        
        service = CompromissoService()
        sucesso = service.excluir_compromisso(compromisso_id, user_id)
        
        if not sucesso:
            return JsonResponse({'error': 'Compromisso não encontrado'}, status=404)
        
        return JsonResponse({
            'success': True,
            'message': 'Compromisso excluído com sucesso!'
        }, json_dumps_params={'ensure_ascii': False})
        
    except PermissionError as e:
        return JsonResponse({'error': str(e)}, status=403)
    except Exception as e:
        return JsonResponse({
            'error': 'Erro ao excluir compromisso',
            'message': str(e)
        }, status=500)
