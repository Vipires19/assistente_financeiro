# 📄 Report Service - Documentação

## 🎯 Sistema de Geração de Relatórios

Service estruturado para gerar relatórios financeiros, preparado para futuras integrações com IA e geração de PDF.

**Localização**: `finance/services/report_service.py`

---

## ✨ Funcionalidades Atuais

### 1. **Relatório Textual**
- Resumo financeiro completo
- Análises (dia, categoria, horário com maior gasto)
- Estatísticas de transações
- Observações baseadas no saldo

### 2. **Formato JSON**
- Retorna dados estruturados
- Inclui metadados e resumo
- Pronto para consumo via API

### 3. **Página HTML**
- Visualização formatada
- Botão de impressão
- Responsivo

---

## 🚀 Como Usar

### Via API

```bash
# Relatório em JSON
GET /finance/api/report/?period=mensal&format=json

# Relatório em texto (JSON com texto)
GET /finance/api/report/?period=mensal&format=text

# Com IA (futuro)
GET /finance/api/report/?period=mensal&format=json&use_ai=true
```

### Via Página HTML

```
GET /finance/report/?period=mensal
```

### Via Botão no Dashboard

O botão "Gerar Relatório" no dashboard:
1. Chama a API
2. Abre relatório em nova aba
3. Mostra loading durante geração

---

## 📋 Estrutura do Relatório

### Resumo Financeiro
- Total de Entradas
- Total de Gastos
- Saldo

### Análises
- Dia com maior gasto
- Categoria com maior gasto
- Horário com maior gasto

### Estatísticas
- Total de transações
- Contagem por tipo (receitas/despesas)

### Observações
- Análise automática do saldo
- Sugestões básicas

---

## 🔮 Preparado para o Futuro

### 1. **Integração com IA**

O método `generate_ai_report()` está preparado:

```python
def generate_ai_report(self, user_id: str, period: str = 'mensal'):
    """
    Gera relatório com análise de IA.
    
    TODO: Integrar com IA para:
    - Análise de padrões de gastos
    - Recomendações personalizadas
    - Insights automáticos
    - Previsões de gastos
    """
```

**Como implementar no futuro**:
1. Adicionar integração com API de IA (OpenAI, Claude, etc.)
2. Enviar dados do dashboard para análise
3. Receber insights e recomendações
4. Incorporar no texto do relatório

**Estrutura preparada**:
```python
report['ai_analysis'] = {
    'enabled': True,
    'insights': [
        'Você gasta 30% mais em fins de semana',
        'Sua categoria Alimentação está acima da média'
    ],
    'recommendations': [
        'Considere reduzir gastos em Lazer',
        'Aumente receitas em 10% para melhorar saldo'
    ]
}
```

---

### 2. **Geração de PDF**

O método `generate_pdf_report()` está preparado:

```python
def generate_pdf_report(self, user_id: str, period: str = 'mensal') -> bytes:
    """
    Gera relatório em PDF.
    
    TODO: Implementar usando:
    - reportlab (Python puro)
    - weasyprint (HTML para PDF)
    - xhtml2pdf
    """
```

**Como implementar no futuro**:

#### Opção 1: Usando reportlab
```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def generate_pdf_report(self, user_id: str, period: str = 'mensal') -> bytes:
    report_data = self.generate_text_report(user_id, period)
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Adiciona conteúdo
    p.drawString(100, 800, report_data['report_text'])
    
    p.showPage()
    p.save()
    
    return buffer.getvalue()
```

#### Opção 2: Usando weasyprint (HTML para PDF)
```python
from weasyprint import HTML

def generate_pdf_report(self, user_id: str, period: str = 'mensal') -> bytes:
    report_data = self.generate_text_report(user_id, period)
    
    # Renderiza template HTML
    html_content = render_to_string('finance/report_pdf.html', {
        'report_text': report_data['report_text'],
        'summary': report_data['summary']
    })
    
    # Converte HTML para PDF
    pdf = HTML(string=html_content).write_pdf()
    
    return pdf
```

---

## 📊 Exemplo de Resposta JSON

```json
{
  "report": "📊 RELATÓRIO FINANCEIRO DO MÊS\n==================================================\n\n💰 RESUMO FINANCEIRO\n...",
  "metadata": {
    "period": "mensal",
    "generated_at": "2024-01-15T10:30:00Z",
    "user_id": "507f1f77bcf86cd799439011",
    "format": "text"
  },
  "summary": {
    "total_expenses": 1500.50,
    "total_income": 3000.00,
    "balance": 1499.50,
    "transactions_count": 45
  }
}
```

---

## 🔧 Métodos Disponíveis

### `generate_text_report(user_id, period)`
Gera relatório textual completo.

### `generate_ai_report(user_id, period)` (Futuro)
Gera relatório com análise de IA.

### `generate_pdf_report(user_id, period)` (Futuro)
Gera relatório em PDF.

### `generate_report(user_id, period, format, use_ai)`
Método principal que escolhe o formato.

---

## 🎨 Template HTML

O template `finance/report.html` inclui:
- ✅ Visualização formatada do relatório
- ✅ Botão de impressão
- ✅ Resumo rápido no topo
- ✅ Metadados (período, data de geração)
- ✅ Estilos para impressão

---

## 📝 Próximos Passos

### Fase 1: IA (Próxima)
- [ ] Integrar com API de IA
- [ ] Adicionar análise de padrões
- [ ] Gerar recomendações automáticas
- [ ] Insights personalizados

### Fase 2: PDF
- [ ] Escolher biblioteca (reportlab ou weasyprint)
- [ ] Criar template PDF
- [ ] Adicionar gráficos ao PDF
- [ ] Estilização profissional

### Fase 3: Exportação
- [ ] Exportar para Excel
- [ ] Exportar para CSV
- [ ] Enviar por email
- [ ] Agendar relatórios

---

## ✅ Vantagens da Estrutura

1. ✅ **Separação de responsabilidades**: Service isolado
2. ✅ **Fácil de estender**: Métodos preparados para IA e PDF
3. ✅ **Múltiplos formatos**: Text, JSON, PDF (futuro)
4. ✅ **Reutilização**: Usa DashboardService existente
5. ✅ **Testável**: Métodos isolados e testáveis

---

## 🔌 Endpoints

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/finance/api/report/` | GET | API de relatórios |
| `/finance/report/` | GET | Página HTML do relatório |

---

## 📋 Parâmetros da API

- `period`: `diário`, `semanal`, `mensal` (default: `mensal`)
- `format`: `text`, `json`, `pdf` (default: `text`)
- `use_ai`: `true`, `false` (default: `false`)

---

## 🐛 Tratamento de Erros

- ✅ Validação de parâmetros
- ✅ Tratamento de exceções
- ✅ Mensagens de erro claras
- ✅ Status HTTP apropriados

