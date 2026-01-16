"""
Service para gerar dados do dashboard financeiro.

Localização: finance/services/dashboard_service.py

Este service gera todas as métricas e dados necessários para o dashboard,
usando agregações do MongoDB para máxima performance.
"""
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
from finance.repositories.transaction_repository import TransactionRepository


class DashboardService:
    """
    Service para gerar dados do dashboard financeiro.
    
    Exemplo de uso:
        service = DashboardService()
        data = service.get_dashboard_data(
            user_id='...',
            period='mensal'
        )
    """
    
    def __init__(self):
        self.transaction_repo = TransactionRepository()
    
    def get_dashboard_data(self, user_id: str, period: str = 'mensal') -> Dict[str, Any]:
        """
        Gera todos os dados do dashboard financeiro.
        
        SEGURANÇA: Todos os dados são filtrados por user_id para garantir isolamento.
        
        Args:
            user_id: ID do usuário (obrigatório)
            period: Período de filtro ('diário', 'semanal', 'mensal')
        
        Returns:
            Dict com todos os dados do dashboard:
            - total_expenses: Total de gastos
            - total_income: Total de entradas
            - balance: Saldo (entradas - gastos)
            - day_with_highest_expense: Dia com maior gasto
            - category_with_highest_expense: Categoria com maior gasto
            - hour_with_highest_expense: Horário com maior gasto
            - transactions: Lista de transações filtradas
        
        Raises:
            ValueError: Se user_id não fornecido
        """
        if not user_id:
            raise ValueError("user_id é obrigatório para acessar dados do dashboard")
        
        # Calcula datas do período
        start_date, end_date = self._get_period_dates(period)
        
        # Executa todas as agregações em paralelo (via pipeline único otimizado)
        data = {
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
        }
        
        # Totais (gastos, entradas, saldo)
        totals = self._get_totals(user_id, start_date, end_date)
        data.update(totals)
        
        # Dia com maior gasto
        data['day_with_highest_expense'] = self._get_day_with_highest_expense(
            user_id, start_date, end_date
        )
        
        # Categoria com maior gasto
        data['category_with_highest_expense'] = self._get_category_with_highest_expense(
            user_id, start_date, end_date
        )
        
        # Horário com maior gasto
        data['hour_with_highest_expense'] = self._get_hour_with_highest_expense(
            user_id, start_date, end_date
        )
        
        # Lista de transações filtradas (sem paginação no método principal)
        transactions_data = self._get_filtered_transactions(
            user_id, start_date, end_date, limit=50, skip=0
        )
        data['transactions'] = transactions_data['transactions']
        data['transactions_pagination'] = transactions_data['pagination']
        
        return data
    
    def _get_period_dates(self, period: str) -> Tuple[datetime, datetime]:
        """
        Calcula as datas de início e fim do período.
        
        Args:
            period: 'diário', 'semanal' ou 'mensal'
        
        Returns:
            Tupla (start_date, end_date)
        """
        end_date = datetime.utcnow()
        
        if period == 'diário':
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'semanal':
            # Últimos 7 dias
            start_date = end_date - timedelta(days=7)
        elif period == 'mensal':
            # Mês atual
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default: mensal
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        return start_date, end_date
    
    def _get_totals(self, user_id: str, start_date: datetime, 
                    end_date: datetime) -> Dict[str, float]:
        """
        Calcula totais de gastos, entradas e saldo usando agregação.
        
        Args:
            user_id: ID do usuário
            start_date: Data inicial
            end_date: Data final
        
        Returns:
            Dict com total_expenses, total_income, balance
        """
        pipeline = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': '$type',
                    'total': {'$sum': '$value'}
                }
            }
        ]
        
        # Acessa collection diretamente para agregações complexas
        # (isso é aceitável para agregações que não são CRUD simples)
        results = list(self.transaction_repo.collection.aggregate(pipeline))
        
        total_income = sum(r['total'] for r in results if r['_id'] == 'income')
        total_expense = sum(r['total'] for r in results if r['_id'] == 'expense')
        
        return {
            'total_expenses': total_expense,
            'total_income': total_income,
            'balance': total_income - total_expense
        }
    
    def _get_day_with_highest_expense(self, user_id: str, start_date: datetime,
                                     end_date: datetime) -> Optional[Dict[str, Any]]:
        """
        Encontra o dia com maior gasto usando agregação.
        
        SEGURANÇA: Sempre filtra por user_id primeiro.
        
        Args:
            user_id: ID do usuário (obrigatório)
            start_date: Data inicial
            end_date: Data final
        
        Returns:
            Dict com date e total, ou None se não houver gastos
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        pipeline = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),  # CRÍTICO: Sempre filtrar por user_id primeiro
                    'type': 'expense',
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': '%Y-%m-%d',
                            'date': '$created_at'
                        }
                    },
                    'total': {'$sum': '$value'},
                    'date': {'$first': '$created_at'}
                }
            },
            {
                '$sort': {'total': -1}
            },
            {
                '$limit': 1
            }
        ]
        
        # Acessa collection diretamente para agregações complexas
        # (isso é aceitável para agregações que não são CRUD simples)
        results = list(self.transaction_repo.collection.aggregate(pipeline))
        
        if results:
            # Formata a data no padrão brasileiro
            date_obj = results[0]['_id']
            if isinstance(date_obj, datetime):
                formatted_date = date_obj.strftime('%d/%m/%Y')
            elif isinstance(date_obj, str):
                # Se for string no formato YYYY-MM-DD, converte
                try:
                    from dateutil import parser
                    dt = parser.parse(date_obj)
                    formatted_date = dt.strftime('%d/%m/%Y')
                except:
                    formatted_date = date_obj
            else:
                formatted_date = str(date_obj)
            
            return {
                'date': results[0]['_id'],
                'total': results[0]['total'],
                'formatted_date': formatted_date
            }
        
        return None
    
    def _get_category_with_highest_expense(self, user_id: str, start_date: datetime,
                                         end_date: datetime) -> Optional[Dict[str, Any]]:
        """
        Encontra a categoria com maior gasto usando agregação.
        
        SEGURANÇA: Sempre filtra por user_id primeiro.
        
        Args:
            user_id: ID do usuário (obrigatório)
            start_date: Data inicial
            end_date: Data final
        
        Returns:
            Dict com category e total, ou None se não houver gastos
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        pipeline = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),  # CRÍTICO: Sempre filtrar por user_id primeiro
                    'type': 'expense',
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': '$category',
                    'total': {'$sum': '$value'},
                    'count': {'$sum': 1}
                }
            },
            {
                '$sort': {'total': -1}
            },
            {
                '$limit': 1
            }
        ]
        
        # Acessa collection diretamente para agregações complexas
        # (isso é aceitável para agregações que não são CRUD simples)
        results = list(self.transaction_repo.collection.aggregate(pipeline))
        
        if results:
            return {
                'category': results[0]['_id'],
                'total': results[0]['total'],
                'count': results[0]['count']
            }
        
        return None
    
    def _get_hour_with_highest_expense(self, user_id: str, start_date: datetime,
                                      end_date: datetime) -> Optional[Dict[str, Any]]:
        """
        Encontra o horário com maior gasto usando agregação.
        
        Usa o campo 'hour' extraído para máxima performance.
        SEGURANÇA: Sempre filtra por user_id primeiro.
        
        Args:
            user_id: ID do usuário (obrigatório)
            start_date: Data inicial
            end_date: Data final
        
        Returns:
            Dict com hour e total, ou None se não houver gastos
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        pipeline = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),  # CRÍTICO: Sempre filtrar por user_id primeiro
                    'type': 'expense',
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': '$hour',
                    'total': {'$sum': '$value'},
                    'count': {'$sum': 1}
                }
            },
            {
                '$sort': {'total': -1}
            },
            {
                '$limit': 1
            }
        ]
        
        # Acessa collection diretamente para agregações complexas
        # (isso é aceitável para agregações que não são CRUD simples)
        results = list(self.transaction_repo.collection.aggregate(pipeline))
        
        if results:
            hour = results[0]['_id']
            return {
                'hour': hour,
                'total': results[0]['total'],
                'count': results[0]['count'],
                'formatted_hour': f"{hour:02d}:00"
            }
        
        return None
    
    def _get_filtered_transactions(self, user_id: str, start_date: datetime,
                                  end_date: datetime, limit: int = 50, 
                                  skip: int = 0) -> Dict[str, Any]:
        """
        Retorna lista de transações filtradas por período com paginação.
        
        SEGURANÇA: Sempre filtra por user_id para garantir isolamento de dados.
        
        Args:
            user_id: ID do usuário (obrigatório)
            start_date: Data inicial
            end_date: Data final
            limit: Limite de resultados por página
            skip: Quantidade a pular (para paginação)
        
        Returns:
            Dict com:
            - transactions: Lista de transações
            - total: Total de transações
            - page: Página atual
            - limit: Limite por página
            - has_next: Se há próxima página
            - has_prev: Se há página anterior
        
        Raises:
            ValueError: Se user_id não fornecido
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        query = {
            'user_id': ObjectId(user_id),  # CRÍTICO: Sempre filtrar por user_id
            'created_at': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        # Conta total de transações
        total = self.transaction_repo.count(query)
        
        # Busca transações com paginação
        transactions = self.transaction_repo.find_many(
            query=query,
            limit=limit,
            skip=skip,
            sort=('created_at', -1)
        )
        
        # Calcula informações de paginação
        current_page = (skip // limit) + 1
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        has_next = skip + limit < total
        has_prev = skip > 0
        
        # Formata transações para resposta
        formatted = []
        for trans in transactions:
            created_at = trans['created_at']
            if isinstance(created_at, datetime):
                date_str = created_at.strftime('%d/%m/%Y')
                time_str = created_at.strftime('%H:%M')
            else:
                # Se for string, tenta converter
                try:
                    from dateutil import parser
                    dt = parser.parse(created_at) if isinstance(created_at, str) else created_at
                    date_str = dt.strftime('%d/%m/%Y')
                    time_str = dt.strftime('%H:%M')
                except:
                    date_str = str(created_at)
                    time_str = ''
            
            formatted.append({
                'id': str(trans['_id']),
                'type': trans['type'],
                'category': trans.get('category', 'outros'),
                'description': trans['description'],
                'value': float(trans['value']),
                'date': date_str,
                'time': time_str,
                'created_at': created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                'hour': trans.get('hour', None)
            })
        
        return {
            'transactions': formatted,
            'pagination': {
                'total': total,
                'page': current_page,
                'limit': limit,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            }
        }
    
    # ==================== MÉTODOS PARA GRÁFICOS (Chart.js) ====================
    
    def get_expenses_by_category_chart_data(self, user_id: str, 
                                           period: str = 'mensal') -> Dict[str, Any]:
        """
        Gera dados para gráfico de despesas e entradas por categoria (Chart.js).
        
        Mostra tanto entradas quanto gastos agrupados por categoria.
        
        Args:
            user_id: ID do usuário
            period: Período ('diário', 'semanal', 'mensal')
        
        Returns:
            Dict no formato Chart.js com dois datasets (entradas e gastos)
        """
        start_date, end_date = self._get_period_dates(period)
        
        # Pipeline para gastos
        pipeline_expenses = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),
                    'type': 'expense',
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': '$category',
                    'total': {'$sum': '$value'}
                }
            },
            {
                '$sort': {'total': -1}
            }
        ]
        
        # Pipeline para entradas
        pipeline_incomes = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),
                    'type': 'income',
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': '$category',
                    'total': {'$sum': '$value'}
                }
            },
            {
                '$sort': {'total': -1}
            }
        ]
        
        results_expenses = list(self.transaction_repo.collection.aggregate(pipeline_expenses))
        results_incomes = list(self.transaction_repo.collection.aggregate(pipeline_incomes))
        
        # Combina todas as categorias (de gastos e entradas)
        all_categories = set()
        for r in results_expenses:
            all_categories.add(r['_id'])
        for r in results_incomes:
            all_categories.add(r['_id'])
        
        labels = sorted(list(all_categories))
        
        # Cria dicionários para acesso rápido
        expenses_dict = {r['_id']: float(r['total']) for r in results_expenses}
        incomes_dict = {r['_id']: float(r['total']) for r in results_incomes}
        
        # Prepara dados
        expenses_data = [expenses_dict.get(cat, 0.0) for cat in labels]
        incomes_data = [incomes_dict.get(cat, 0.0) for cat in labels]
        
        # Paleta de cores determinística
        color_palette = [
            'rgba(239, 68, 68, 0.6)',   # Vermelho (gastos)
            'rgba(34, 197, 94, 0.6)',   # Verde (entradas)
            'rgba(59, 130, 246, 0.6)',  # Azul
            'rgba(168, 85, 247, 0.6)',  # Roxo
            'rgba(251, 146, 60, 0.6)',  # Laranja
            'rgba(236, 72, 153, 0.6)',  # Rosa
            'rgba(14, 165, 233, 0.6)',  # Ciano
            'rgba(132, 204, 22, 0.6)',  # Lima
            'rgba(245, 158, 11, 0.6)',  # Amarelo
            'rgba(139, 92, 246, 0.6)',  # Violeta
        ]
        
        background_colors = []
        border_colors = []
        
        for label in labels:
            color_index = hash(label) % len(color_palette)
            color = color_palette[abs(color_index)]
            background_colors.append(color.replace('0.6', '0.2'))
            border_colors.append(color.replace('0.6', '1'))
        
        if len(labels) == 0:
            labels = ['Nenhum dado']
            expenses_data = [0]
            incomes_data = [0]
            background_colors = ['rgba(200, 200, 200, 0.2)']
            border_colors = ['rgba(200, 200, 200, 1)']
        
        return {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Gastos',
                    'data': expenses_data,
                    'backgroundColor': 'rgba(239, 68, 68, 0.2)',
                    'borderColor': 'rgba(239, 68, 68, 1)',
                    'borderWidth': 2
                },
                {
                    'label': 'Entradas',
                    'data': incomes_data,
                    'backgroundColor': 'rgba(34, 197, 94, 0.2)',
                    'borderColor': 'rgba(34, 197, 94, 1)',
                    'borderWidth': 2
                }
            ]
        }
    
    def get_expenses_by_weekday_chart_data(self, user_id: str,
                                          period: str = 'mensal') -> Dict[str, Any]:
        """
        Gera dados para gráfico de despesas por dia da semana (Chart.js).
        
        SEGURANÇA: Sempre filtra por user_id primeiro.
        
        Args:
            user_id: ID do usuário (obrigatório)
            period: Período ('diário', 'semanal', 'mensal')
        
        Returns:
            Dict no formato Chart.js
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        start_date, end_date = self._get_period_dates(period)
        
        # Nomes dos dias da semana em português
        weekday_names = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
        
        # Busca todas as transações de despesas no período
        query = {
            'user_id': ObjectId(user_id),
            'type': 'expense',
            'created_at': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        transactions = self.transaction_repo.find_many(query=query, limit=10000)
        
        # Nomes dos dias da semana em português (0=Segunda, 6=Domingo)
        weekday_names = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
        
        # Cria array com 7 posições (uma para cada dia da semana)
        # Python weekday(): 0=Segunda, 1=Terça, ..., 6=Domingo
        data_by_weekday = [0.0] * 7
        
        for trans in transactions:
            created_at = trans.get('created_at')
            if isinstance(created_at, datetime):
                # weekday() retorna 0 (Segunda) a 6 (Domingo)
                weekday_index = created_at.weekday()
                if 0 <= weekday_index < 7:
                    data_by_weekday[weekday_index] += float(trans.get('value', 0))
        
        return {
            'labels': weekday_names,
            'datasets': [{
                'label': 'Gastos por Dia da Semana',
                'data': data_by_weekday,
                'backgroundColor': 'rgba(239, 68, 68, 0.5)',
                'borderColor': 'rgba(239, 68, 68, 1)',
                'borderWidth': 2
            }]
        }
    
    def get_expenses_by_hour_chart_data(self, user_id: str,
                                       period: str = 'mensal') -> Dict[str, Any]:
        """
        Gera dados para gráfico de despesas por horário do dia (Chart.js).
        
        Usa o campo 'hour' extraído para máxima performance.
        SEGURANÇA: Sempre filtra por user_id primeiro.
        
        Args:
            user_id: ID do usuário (obrigatório)
            period: Período ('diário', 'semanal', 'mensal')
        
        Returns:
            Dict no formato Chart.js
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        start_date, end_date = self._get_period_dates(period)
        
        pipeline = [
            {
                '$match': {
                    'user_id': ObjectId(user_id),  # CRÍTICO: Sempre filtrar por user_id primeiro
                    'type': 'expense',
                    'created_at': {
                        '$gte': start_date,
                        '$lte': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': '$hour',  # Campo extraído - muito rápido!
                    'total': {'$sum': '$value'}
                }
            },
            {
                '$sort': {'_id': 1}
            }
        ]
        
        results = list(self.transaction_repo.collection.aggregate(pipeline))
        
        # Cria array com 24 posições (uma para cada hora)
        labels = [f"{h:02d}:00" for h in range(24)]
        data_by_hour = [0.0] * 24
        
        for result in results:
            hour = result['_id']
            if 0 <= hour < 24:
                data_by_hour[hour] = float(result['total'])
        
        return {
            'labels': labels,
            'datasets': [{
                'label': 'Gastos por Horário',
                'data': data_by_hour,
                'backgroundColor': 'rgba(239, 68, 68, 0.2)',
                'borderColor': 'rgba(239, 68, 68, 1)',
                'borderWidth': 2,
                'fill': True,
                'tension': 0.4
            }]
        }
    
    def get_all_charts_data(self, user_id: str, period: str = 'mensal') -> Dict[str, Any]:
        """
        Gera todos os dados de gráficos de uma vez.
        
        Args:
            user_id: ID do usuário
            period: Período ('diário', 'semanal', 'mensal')
        
        Returns:
            Dict com todos os dados de gráficos:
            {
                'by_category': {...},
                'by_weekday': {...},
                'by_hour': {...}
            }
        """
        return {
            'by_category': self.get_expenses_by_category_chart_data(user_id, period),
            'by_weekday': self.get_expenses_by_weekday_chart_data(user_id, period),
            'by_hour': self.get_expenses_by_hour_chart_data(user_id, period)
        }

