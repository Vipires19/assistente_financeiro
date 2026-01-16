# 📊 Dashboard Template - Documentação

## 🎨 Template HTML do Dashboard Financeiro

Template completo e responsivo para o dashboard financeiro.

**Localização**: `templates/finance/dashboard.html`

---

## ✨ Funcionalidades

### 1. **Cards de Métricas** (Topo)
- ✅ Gastos (vermelho)
- ✅ Entradas (verde)
- ✅ Saldo (verde/vermelho conforme valor)
- ✅ Dia com maior gasto
- ✅ Categoria com maior gasto
- ✅ Horário com maior gasto

### 2. **Filtro de Período**
- ✅ Dropdown com opções: Diário, Semanal, Mensal
- ✅ Atualiza todos os dados ao mudar período

### 3. **Gráficos** (Chart.js)
- ✅ Despesas por Categoria (Doughnut)
- ✅ Despesas por Dia da Semana (Bar)
- ✅ Despesas por Horário do Dia (Line)

### 4. **Tabela de Transações**
- ✅ Responsiva com scroll horizontal no mobile
- ✅ Colunas: Data, Tipo, Categoria, Descrição, Valor
- ✅ Cores diferentes para receitas/despesas

### 5. **Botão Gerar Relatório**
- ✅ Pronto para implementação futura

---

## 📱 Layout

### Mobile-First
- ✅ Grid responsivo (1 coluna no mobile, 2-3 no desktop)
- ✅ Cards empilhados verticalmente
- ✅ Tabela com scroll horizontal
- ✅ Gráficos adaptáveis

### Desktop
- ✅ 3 colunas para cards principais
- ✅ 2 colunas para gráficos (3º gráfico ocupa 2 colunas)
- ✅ Tabela completa visível

---

## 🎯 Estrutura

```
Header (sticky)
  ├── Título
  └── Email + Logout

Filtro de Período
  ├── Dropdown
  └── Botão Gerar Relatório

Cards de Métricas (6 cards)
  ├── Gastos
  ├── Entradas
  ├── Saldo
  ├── Dia com Maior Gasto
  ├── Categoria com Maior Gasto
  └── Horário com Maior Gasto

Seção de Gráficos
  ├── Despesas por Categoria (Doughnut)
  ├── Despesas por Dia da Semana (Bar)
  └── Despesas por Horário (Line)

Tabela de Transações
  └── Scroll horizontal no mobile
```

---

## 🔌 API Endpoints

O template consome as seguintes APIs:

### 1. Dashboard Data
```
GET /finance/api/dashboard/?period=mensal
```

**Resposta**:
```json
{
  "total_expenses": 1500.50,
  "total_income": 3000.00,
  "balance": 1499.50,
  "day_with_highest_expense": {...},
  "category_with_highest_expense": {...},
  "hour_with_highest_expense": {...},
  "transactions": [...]
}
```

### 2. Charts Data
```
GET /finance/api/charts/?type=all&period=mensal
```

**Resposta**:
```json
{
  "by_category": {...},
  "by_weekday": {...},
  "by_hour": {...}
}
```

---

## 🚀 Como Usar

### 1. Acessar o Dashboard

```
http://localhost:8000/finance/dashboard/
```

### 2. Requer Autenticação

O dashboard requer autenticação via middleware MongoDB.

### 3. Funcionalidades JavaScript

- **Carregamento automático**: Dados carregam ao abrir a página
- **Filtro de período**: Atualiza dados ao mudar período
- **Gráficos interativos**: Chart.js renderiza gráficos
- **Tabela responsiva**: Scroll horizontal no mobile

---

## 🎨 Estilização

### TailwindCSS
- ✅ Utility classes
- ✅ Responsive breakpoints
- ✅ Cores customizadas (primary)
- ✅ Shadows e borders sutis

### Cores
- **Gastos**: Vermelho (`text-red-600`)
- **Entradas**: Verde (`text-green-600`)
- **Saldo**: Verde (positivo) / Vermelho (negativo)
- **Cards**: Branco com borda cinza

---

## 📊 Gráficos

### Chart.js Configuração

#### 1. Despesas por Categoria (Doughnut)
```javascript
{
  type: 'doughnut',
  responsive: true,
  maintainAspectRatio: false
}
```

#### 2. Despesas por Dia da Semana (Bar)
```javascript
{
  type: 'bar',
  responsive: true,
  scales: { y: { beginAtZero: true } }
}
```

#### 3. Despesas por Horário (Line)
```javascript
{
  type: 'line',
  responsive: true,
  scales: { y: { beginAtZero: true } }
}
```

---

## 📱 Responsividade

### Mobile (< 640px)
- 1 coluna para cards
- Gráficos empilhados
- Tabela com scroll horizontal
- Filtro e botão empilhados

### Tablet (640px - 1024px)
- 2 colunas para cards
- 2 colunas para gráficos
- Tabela completa

### Desktop (> 1024px)
- 3 colunas para cards
- 2 colunas para gráficos (3º ocupa 2)
- Tabela completa

---

## 🔧 Funções JavaScript

### `loadDashboardData(period)`
Carrega dados principais do dashboard via API.

### `loadCharts(period)`
Carrega e renderiza gráficos via API.

### `updateTransactionsTable(transactions)`
Atualiza tabela de transações.

### `reloadDashboard()`
Recarrega todos os dados e gráficos.

### `formatCurrency(value)`
Formata valores monetários (R$).

### `formatDate(dateString)`
Formata datas (DD/MM/YYYY HH:MM).

---

## ✅ Recursos Implementados

- ✅ Layout minimalista
- ✅ Mobile-first
- ✅ 6 cards de métricas
- ✅ 3 gráficos interativos
- ✅ Tabela responsiva
- ✅ Filtro de período
- ✅ Botão gerar relatório
- ✅ TailwindCSS
- ✅ Scroll horizontal no mobile
- ✅ Chart.js integrado
- ✅ API endpoints configurados

---

## 🐛 Troubleshooting

### Gráficos não aparecem
- Verifique se Chart.js está carregado
- Verifique console do navegador para erros
- Confirme que API retorna dados no formato correto

### Tabela não responsiva
- Verifique se `overflow-x-auto` está aplicado
- Confirme que tabela está dentro de container com largura limitada

### Dados não carregam
- Verifique autenticação (middleware)
- Confirme URLs da API estão corretas
- Verifique console do navegador para erros de fetch

---

## 📝 Próximos Passos

- [ ] Implementar geração de relatório (PDF/Excel)
- [ ] Adicionar loading states
- [ ] Adicionar tratamento de erros
- [ ] Adicionar paginação na tabela
- [ ] Adicionar filtros na tabela
- [ ] Adicionar exportação de dados

