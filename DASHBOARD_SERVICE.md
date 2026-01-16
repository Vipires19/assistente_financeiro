# 📊 Dashboard Service - Documentação

## 🎯 Service de Dashboard Financeiro

Service responsável por gerar todos os dados do dashboard financeiro usando agregações do MongoDB.

**Localização**: `finance/services/dashboard_service.py`

---

## 📥 Entrada

```python
get_dashboard_data(
    user_id: str,        # ID do usuário
    period: str = 'mensal'  # Período: 'diário', 'semanal' ou 'mensal'
)
```

---

## 📤 Saída

```python
{
    'period': str,                    # Período usado
    'start_date': datetime,           # Data inicial do período
    'end_date': datetime,             # Data final do período
    
    # Totais
    'total_expenses': float,           # Total de gastos
    'total_income': float,            # Total de entradas
    'balance': float,                 # Saldo (entradas - gastos)
    
    # Análises
    'day_with_highest_expense': {     # Dia com maior gasto
        'date': str,                  # Data (YYYY-MM-DD)
        'total': float,               # Total gasto no dia
        'formatted_date': str         # Data formatada
    } | None,
    
    'category_with_highest_expense': {  # Categoria com maior gasto
        'category': str,              # Nome da categoria
        'total': float,               # Total gasto na categoria
        'count': int                  # Quantidade de transações
    } | None,
    
    'hour_with_highest_expense': {    # Horário com maior gasto
        'hour': int,                  # Hora (0-23)
        'total': float,                # Total gasto no horário
        'count': int,                  # Quantidade de transações
        'formatted_hour': str          # Hora formatada (HH:00)
    } | None,
    
    'transactions': [                 # Lista de transações filtradas
        {
            'id': str,
            'type': str,               # 'expense' | 'income'
            'category': str,
            'description': str,
            'value': float,
            'created_at': str,         # ISO format
            'hour': int                # 0-23
        },
        ...
    ]
}
```

---

## 🔄 Períodos Suportados

### Diário
- **Período**: Hoje (00:00 até agora)
- **Uso**: Análise do dia atual

### Semanal
- **Período**: Últimos 7 dias
- **Uso**: Análise da semana

### Mensal
- **Período**: Mês atual (dia 1 até agora)
- **Uso**: Análise do mês

---

## 🚀 Exemplo de Uso

```python
from finance.services.dashboard_service import DashboardService

service = DashboardService()

# Dashboard mensal
data = service.get_dashboard_data(
    user_id='507f1f77bcf86cd799439011',
    period='mensal'
)

print(f"Total de gastos: R$ {data['total_expenses']:.2f}")
print(f"Total de entradas: R$ {data['total_income']:.2f}")
print(f"Saldo: R$ {data['balance']:.2f}")

if data['day_with_highest_expense']:
    day = data['day_with_highest_expense']
    print(f"Dia com maior gasto: {day['formatted_date']} - R$ {day['total']:.2f}")

if data['category_with_highest_expense']:
    cat = data['category_with_highest_expense']
    print(f"Categoria com maior gasto: {cat['category']} - R$ {cat['total']:.2f}")

if data['hour_with_highest_expense']:
    hour = data['hour_with_highest_expense']
    print(f"Horário com maior gasto: {hour['formatted_hour']} - R$ {hour['total']:.2f}")

print(f"\nTransações ({len(data['transactions'])}):")
for trans in data['transactions'][:5]:  # Primeiras 5
    print(f"  - {trans['description']}: R$ {trans['value']:.2f}")
```

---

## ⚡ Performance

Todas as métricas são calculadas usando **agregações do MongoDB**, garantindo:

- ✅ **Performance otimizada**: Queries executadas no banco
- ✅ **Índices utilizados**: Aproveita índices compostos
- ✅ **Cálculos no backend**: Nenhuma dependência do frontend
- ✅ **Escalável**: Funciona bem com grandes volumes de dados

### Tempo de Execução Esperado

| Métrica | Tempo |
|---------|-------|
| Totais | 5-15ms |
| Dia com maior gasto | 10-30ms |
| Categoria com maior gasto | 10-30ms |
| Horário com maior gasto | 5-15ms |
| Lista de transações | 5-20ms |
| **Total** | **35-110ms** |

---

## 📊 Agregações Utilizadas

### 1. Totais (Gastos, Entradas, Saldo)

```javascript
[
  {
    $match: {
      user_id: ObjectId("..."),
      created_at: { $gte: start_date, $lte: end_date }
    }
  },
  {
    $group: {
      _id: "$type",
      total: { $sum: "$value" }
    }
  }
]
```

**Índice usado**: `[user_id, created_at]`

---

### 2. Dia com Maior Gasto

```javascript
[
  {
    $match: {
      user_id: ObjectId("..."),
      type: "expense",
      created_at: { $gte: start_date, $lte: end_date }
    }
  },
  {
    $group: {
      _id: { $dateToString: { format: "%Y-%m-%d", date: "$created_at" } },
      total: { $sum: "$value" }
    }
  },
  { $sort: { total: -1 } },
  { $limit: 1 }
]
```

**Índice usado**: `[user_id, created_at]` + `[user_id, type]`

---

### 3. Categoria com Maior Gasto

```javascript
[
  {
    $match: {
      user_id: ObjectId("..."),
      type: "expense",
      created_at: { $gte: start_date, $lte: end_date }
    }
  },
  {
    $group: {
      _id: "$category",
      total: { $sum: "$value" },
      count: { $sum: 1 }
    }
  },
  { $sort: { total: -1 } },
  { $limit: 1 }
]
```

**Índice usado**: `[user_id, category]` + `[user_id, type]`

---

### 4. Horário com Maior Gasto

```javascript
[
  {
    $match: {
      user_id: ObjectId("..."),
      type: "expense",
      created_at: { $gte: start_date, $lte: end_date }
    }
  },
  {
    $group: {
      _id: "$hour",  // ✅ Campo extraído - muito rápido!
      total: { $sum: "$value" },
      count: { $sum: 1 }
    }
  },
  { $sort: { total: -1 } },
  { $limit: 1 }
]
```

**Índice usado**: `[user_id, type]` + campo `hour` extraído

---

### 5. Lista de Transações Filtradas

```javascript
{
  user_id: ObjectId("..."),
  created_at: { $gte: start_date, $lte: end_date }
}
.sort({ created_at: -1 })
.limit(50)
```

**Índice usado**: `[user_id, created_at]` (desc)

---

## 🎯 Integração com Views

### Exemplo de View

```python
from finance.services.dashboard_service import DashboardService
from django.http import JsonResponse

def dashboard_view(request):
    if not hasattr(request, 'user_mongo') or not request.user_mongo:
        return JsonResponse({'error': 'Não autenticado'}, status=401)
    
    period = request.GET.get('period', 'mensal')
    
    service = DashboardService()
    data = service.get_dashboard_data(
        user_id=str(request.user_mongo['_id']),
        period=period
    )
    
    return JsonResponse(data)
```

---

## 🔧 Métodos Internos

### `_get_period_dates(period: str) -> Tuple[datetime, datetime]`
Calcula as datas de início e fim do período.

### `_get_totals(user_id, start_date, end_date) -> Dict`
Calcula totais usando agregação MongoDB.

### `_get_day_with_highest_expense(user_id, start_date, end_date) -> Dict | None`
Encontra o dia com maior gasto usando agregação.

### `_get_category_with_highest_expense(user_id, start_date, end_date) -> Dict | None`
Encontra a categoria com maior gasto usando agregação.

### `_get_hour_with_highest_expense(user_id, start_date, end_date) -> Dict | None`
Encontra o horário com maior gasto usando agregação (campo `hour` extraído).

### `_get_filtered_transactions(user_id, start_date, end_date, limit=50) -> List`
Retorna lista de transações filtradas e formatadas.

---

## ✅ Vantagens

1. ✅ **Tudo no backend**: Nenhuma dependência do frontend
2. ✅ **Agregações MongoDB**: Performance otimizada
3. ✅ **Índices utilizados**: Queries rápidas
4. ✅ **Código limpo**: Separação de responsabilidades
5. ✅ **Fácil de testar**: Métodos isolados
6. ✅ **Escalável**: Funciona com grandes volumes

---

## 🐛 Tratamento de Erros

- Se não houver transações no período, retorna `None` para análises
- Totais retornam `0.0` se não houver dados
- Lista de transações retorna `[]` se vazia

---

## 📝 Notas

- Todas as datas são em UTC
- Valores sempre em float (precisão decimal)
- Campo `hour` extraído é usado para máxima performance
- Limite padrão de transações: 50 (configurável)

