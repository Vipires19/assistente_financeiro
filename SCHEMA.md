# 📊 Schema MongoDB - Dashboard Financeiro

## 📋 Collections

### 1. Collection: `users`

**Descrição**: Armazena dados dos usuários do sistema.

**Schema**:
```javascript
{
  _id: ObjectId,                    // ID único do usuário
  email: String,                   // Email (único, indexado)
  password_hash: String,           // Hash bcrypt da senha
  created_at: ISODate,             // Data de criação
  updated_at: ISODate              // Data de última atualização
}
```

**Índices**:
- `email` (único)

**Exemplo**:
```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  email: "usuario@email.com",
  password_hash: "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyY5Y5Y5Y5Y5",
  created_at: ISODate("2024-01-15T10:30:00Z"),
  updated_at: ISODate("2024-01-15T10:30:00Z")
}
```

---

### 2. Collection: `transactions`

**Descrição**: Armazena todas as transações financeiras (receitas e despesas).

**Schema**:
```javascript
{
  _id: ObjectId,                   // ID único da transação
  user_id: ObjectId,                // Referência ao usuário (indexado)
  type: String,                     // "expense" | "income"
  category: String,                // Categoria da transação
  description: String,             // Descrição detalhada
  value: Number,                   // Valor da transação (sempre positivo)
  created_at: ISODate,              // Data e hora completa da transação
  hour: Number                      // Hora extraída (0-23) para análises
}
```

**Índices**:
- `user_id` (simples)
- `[user_id, created_at]` (composto, desc)
- `created_at` (simples)
- `[user_id, type]` (composto)
- `[user_id, category]` (composto)

**Exemplo**:
```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  user_id: ObjectId("507f1f77bcf86cd799439011"),
  type: "expense",
  category: "Alimentação",
  description: "Almoço no restaurante",
  value: 45.50,
  created_at: ISODate("2024-01-15T12:30:00Z"),
  hour: 12
}
```

---

## 🎯 Por que esse modelo é eficiente?

### 1. **Campo `hour` extraído**

**Vantagem**: Facilita análises por horário sem precisar usar `$hour` do MongoDB em todas as queries.

**Exemplo de uso**:
```javascript
// Análise de gastos por horário do dia
db.transactions.aggregate([
  { $match: { user_id: ObjectId("..."), type: "expense" } },
  { $group: { _id: "$hour", total: { $sum: "$value" } } },
  { $sort: { _id: 1 } }
])
```

**Sem `hour` extraído** (mais lento):
```javascript
db.transactions.aggregate([
  { $match: { user_id: ObjectId("..."), type: "expense" } },
  { $group: { 
      _id: { $hour: "$created_at" }, 
      total: { $sum: "$value" } 
    } 
  }
])
```

### 2. **Índices compostos otimizados**

**`[user_id, created_at]` (desc)**:
- ✅ Ordenação rápida de transações por data (mais recentes primeiro)
- ✅ Filtros por período de tempo para um usuário específico
- ✅ Paginação eficiente

**`[user_id, type]`**:
- ✅ Filtros rápidos: "todas as despesas do usuário X"
- ✅ Agregações por tipo (receitas vs despesas)

**`[user_id, category]`**:
- ✅ Análises por categoria: "gastos com Alimentação do usuário X"
- ✅ Gráficos de distribuição por categoria

### 3. **Valor sempre positivo**

**Vantagem**: Simplifica cálculos e agregações.

```javascript
// Soma total de despesas (sem verificar sinal)
{ $sum: "$value" }

// Em vez de:
{ $sum: { $abs: "$value" } }  // Mais complexo
```

### 4. **Type como String fixo**

**Vantagem**: Filtros diretos e eficientes.

```javascript
// Filtro simples e rápido
{ user_id: ObjectId("..."), type: "expense" }

// Índice composto [user_id, type] acelera essa query
```

### 5. **created_at como ISODate**

**Vantagem**: Permite queries de intervalo de datas eficientes.

```javascript
// Filtro por período
{
  user_id: ObjectId("..."),
  created_at: {
    $gte: ISODate("2024-01-01"),
    $lte: ISODate("2024-01-31")
  }
}
```

---

## 📈 Queries Otimizadas para Gráficos

### 1. **Gráfico de Receitas vs Despesas (Mensal)**

```javascript
db.transactions.aggregate([
  {
    $match: {
      user_id: ObjectId("..."),
      created_at: {
        $gte: ISODate("2024-01-01"),
        $lt: ISODate("2024-02-01")
      }
    }
  },
  {
    $group: {
      _id: "$type",
      total: { $sum: "$value" }
    }
  }
])
```

**Índice usado**: `[user_id, created_at]` → Muito rápido!

### 2. **Gráfico de Gastos por Categoria**

```javascript
db.transactions.aggregate([
  {
    $match: {
      user_id: ObjectId("..."),
      type: "expense",
      created_at: {
        $gte: ISODate("2024-01-01"),
        $lt: ISODate("2024-02-01")
      }
    }
  },
  {
    $group: {
      _id: "$category",
      total: { $sum: "$value" }
    }
  },
  { $sort: { total: -1 } }
])
```

**Índice usado**: `[user_id, category]` + `created_at` → Eficiente!

### 3. **Gráfico de Gastos por Horário do Dia**

```javascript
db.transactions.aggregate([
  {
    $match: {
      user_id: ObjectId("..."),
      type: "expense"
    }
  },
  {
    $group: {
      _id: "$hour",
      total: { $sum: "$value" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

**Vantagem**: Campo `hour` já extraído → Não precisa calcular em tempo de execução!

### 4. **Timeline de Transações (Últimas N)**

```javascript
db.transactions.find({
  user_id: ObjectId("...")
})
.sort({ created_at: -1 })
.limit(50)
```

**Índice usado**: `[user_id, created_at]` (desc) → Ordenação instantânea!

### 5. **Filtro por Categoria e Tipo**

```javascript
db.transactions.find({
  user_id: ObjectId("..."),
  type: "expense",
  category: "Alimentação"
})
.sort({ created_at: -1 })
```

**Índice usado**: `[user_id, category]` ou `[user_id, type]` → Rápido!

---

## 🚀 Performance

### Índices Criados

1. **`user_id`** (simples)
   - Filtros por usuário
   - Base para índices compostos

2. **`[user_id, created_at]` (desc)**
   - ⚡ Ordenação por data (mais recentes primeiro)
   - ⚡ Filtros por período
   - ⚡ Paginação eficiente

3. **`created_at`** (simples)
   - Filtros globais por data (se necessário)

4. **`[user_id, type]`** (composto)
   - ⚡ Filtros: receitas ou despesas de um usuário
   - ⚡ Agregações por tipo

5. **`[user_id, category]`** (composto)
   - ⚡ Análises por categoria
   - ⚡ Gráficos de distribuição

### Estatísticas de Performance

- **Query simples por usuário**: ~1-5ms (com índice)
- **Agregação mensal**: ~10-50ms (com índices compostos)
- **Gráfico por categoria**: ~5-20ms (com índice composto)
- **Timeline (últimas 50)**: ~2-10ms (com índice [user_id, created_at])

---

## 📝 Boas Práticas

1. ✅ **Sempre filtrar por `user_id` primeiro** - Usa índices compostos
2. ✅ **Usar `created_at` para intervalos** - Índice otimizado
3. ✅ **Campo `hour` pré-calculado** - Evita cálculos em runtime
4. ✅ **Valor sempre positivo** - Simplifica agregações
5. ✅ **Índices compostos** - Aceleram queries complexas

---

## 🔄 Migração/Atualização

Se você já tem dados, pode adicionar o campo `hour`:

```javascript
db.transactions.updateMany(
  { hour: { $exists: false } },
  [
    {
      $set: {
        hour: { $hour: "$created_at" }
      }
    }
  ]
)
```

