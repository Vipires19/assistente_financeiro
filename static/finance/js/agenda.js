/**
 * Agenda JavaScript - FullCalendar Integration
 * Gerencia eventos de compromissos com interações AJAX
 */

const API_BASE = '/finance/api';

// Objeto principal do calendário
const calendario = {
    calendar: null,
    compromissoAtual: null,
    viewType: 'dayGridMonth',
    
    init() {
        const calendarEl = document.getElementById('calendar');
        
        if (!calendarEl) {
            console.error('Elemento #calendar não encontrado');
            return;
        }
        
        // Obter view inicial do seletor se existir
        const filtroView = document.getElementById('filtro-view');
        if (filtroView) {
            this.viewType = filtroView.value || 'dayGridMonth';
        }
        
        this.calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: this.viewType,
            locale: 'pt-br',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay'
            },
            editable: true,
            selectable: true,
            select: this.onSelect.bind(this),
            eventClick: this.onEventClick.bind(this),
            eventDrop: this.onEventDrop.bind(this),
            events: this.fetchEvents.bind(this),
            height: 'auto',
            slotMinTime: '06:00:00',
            slotMaxTime: '22:00:00',
            allDaySlot: false,
            // Sincronizar mudanças de view
            viewDidMount: (view) => {
                if (filtroView && filtroView.value !== view.type) {
                    filtroView.value = view.type;
                    this.viewType = view.type;
                }
            }
        });
        
        this.calendar.render();
        
        // Event listeners
        document.getElementById('addCompromissoBtn').addEventListener('click', () => {
            this.abrirModal();
        });
        
        document.getElementById('closeModal').addEventListener('click', () => {
            this.fecharModal();
        });
        
        document.getElementById('cancelBtn').addEventListener('click', () => {
            this.fecharModal();
        });
        
        document.getElementById('compromissoForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.salvarCompromisso();
        });
        
        document.getElementById('deleteBtn').addEventListener('click', () => {
            this.excluirCompromisso();
        });
        
        // Event listener para filtro de visualização
        if (filtroView) {
            filtroView.addEventListener('change', (e) => {
                this.viewType = e.target.value;
                this.calendar.changeView(this.viewType);
            });
        }
    },
    
    fetchEvents(info, successCallback, failureCallback) {
        const start = info.startStr;
        const end = info.endStr;
        
        fetch(`${API_BASE}/agenda/?start=${start}&end=${end}`)
            .then(response => response.json())
            .then(data => {
                successCallback(data);
            })
            .catch(error => {
                console.error('Erro ao buscar compromissos:', error);
                failureCallback(error);
            });
    },
    
    onSelect(selectInfo) {
        // Quando o usuário seleciona um intervalo de datas
        const start = selectInfo.start;
        const end = selectInfo.end || new Date(start.getTime() + 60 * 60 * 1000); // 1 hora depois se não houver end
        const data = start.toISOString().split('T')[0];
        const hora = start.toTimeString().split(' ')[0].substring(0, 5);
        const hora_fim = end.toTimeString().split(' ')[0].substring(0, 5);
        
        this.abrirModal();
        document.getElementById('data').value = data;
        document.getElementById('hora').value = hora;
        document.getElementById('hora_fim').value = hora_fim;
    },
    
    onEventClick(clickInfo) {
        // Quando o usuário clica em um evento
        const evento = clickInfo.event;
        const compromissoId = evento.id;
        
        this.carregarCompromisso(compromissoId);
    },
    
    onEventDrop(dropInfo) {
        // Quando o usuário arrasta um evento para outra data/hora
        const evento = dropInfo.event;
        const start = evento.start;
        const data = start.toISOString().split('T')[0];
        const hora = start.toTimeString().split(' ')[0].substring(0, 5);
        
        this.atualizarDataHora(evento.id, data, hora);
    },
    
    async carregarCompromisso(compromissoId) {
        try {
            // Buscar compromisso via API
            const response = await fetch(`${API_BASE}/agenda/?start=2000-01-01&end=2100-12-31`);
            const eventos = await response.json();
            const evento = eventos.find(e => e.id === compromissoId);
            
            if (!evento) {
                alert('Compromisso não encontrado');
                return;
            }
            
            // Extrair data e hora do evento
            const start = new Date(evento.start);
            const end = evento.end ? new Date(evento.end) : new Date(start.getTime() + 60 * 60 * 1000);
            const data = start.toISOString().split('T')[0];
            const hora = start.toTimeString().split(' ')[0].substring(0, 5);
            const hora_fim = end.toTimeString().split(' ')[0].substring(0, 5);
            
            // Preencher formulário
            document.getElementById('compromissoId').value = compromissoId;
            document.getElementById('titulo').value = evento.title;
            document.getElementById('descricao').value = evento.description || '';
            document.getElementById('data').value = data;
            document.getElementById('hora').value = hora;
            document.getElementById('hora_fim').value = hora_fim;
            document.getElementById('tipo').value = evento.extendedProps?.tipo || '';
            document.getElementById('status').value = evento.extendedProps?.status || 'pendente';
            
            document.getElementById('modalTitle').textContent = 'Editar Compromisso';
            document.getElementById('deleteBtn').classList.remove('hidden');
            
            this.compromissoAtual = compromissoId;
            this.abrirModal();
            
        } catch (error) {
            console.error('Erro ao carregar compromisso:', error);
            alert('Erro ao carregar compromisso');
        }
    },
    
    async salvarCompromisso() {
        const compromissoId = document.getElementById('compromissoId').value;
        const titulo = document.getElementById('titulo').value.trim();
        const descricao = document.getElementById('descricao').value.trim();
        const data = document.getElementById('data').value;
        const hora = document.getElementById('hora').value;
        const hora_fim = document.getElementById('hora_fim').value;
        const tipo = document.getElementById('tipo').value;
        const status = document.getElementById('status').value;
        
        if (!titulo || !data || !hora || !hora_fim) {
            alert('Por favor, preencha todos os campos obrigatórios');
            return;
        }
        
        // Validar que hora_fim é posterior a hora
        if (hora_fim <= hora) {
            alert('O horário de término deve ser posterior ao horário de início');
            return;
        }
        
        try {
            let response;
            
            if (compromissoId) {
                // Atualizar compromisso existente
                response = await fetch(`${API_BASE}/compromissos/${compromissoId}/update/`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        titulo,
                        descricao,
                        data,
                        hora,
                        hora_fim,
                        tipo,
                        status
                    })
                });
            } else {
                // Criar novo compromisso
                response = await fetch(`${API_BASE}/compromissos/create/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        titulo,
                        descricao,
                        data,
                        hora,
                        hora_fim,
                        tipo
                    })
                });
            }
            
            const result = await response.json();
            
            if (result.success || response.ok) {
                alert(result.message || 'Compromisso salvo com sucesso!');
                this.fecharModal();
                this.calendar.refetchEvents();
            } else {
                alert(result.error || 'Erro ao salvar compromisso');
            }
            
        } catch (error) {
            console.error('Erro ao salvar compromisso:', error);
            alert('Erro ao salvar compromisso');
        }
    },
    
    async atualizarDataHora(compromissoId, data, hora) {
        try {
            const response = await fetch(`${API_BASE}/compromissos/${compromissoId}/update/`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    data,
                    hora
                })
            });
            
            const result = await response.json();
            
            if (!result.success && !response.ok) {
                // Reverter mudança se falhar
                this.calendar.refetchEvents();
                alert('Erro ao atualizar data/hora do compromisso');
            }
            
        } catch (error) {
            console.error('Erro ao atualizar data/hora:', error);
            this.calendar.refetchEvents();
            alert('Erro ao atualizar data/hora do compromisso');
        }
    },
    
    async excluirCompromisso() {
        const compromissoId = document.getElementById('compromissoId').value;
        
        if (!compromissoId) {
            return;
        }
        
        if (!confirm('Tem certeza que deseja excluir este compromisso?')) {
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/compromissos/${compromissoId}/delete/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': this.getCsrfToken()
                }
            });
            
            const result = await response.json();
            
            if (result.success || response.ok) {
                alert('Compromisso excluído com sucesso!');
                this.fecharModal();
                this.calendar.refetchEvents();
            } else {
                alert(result.error || 'Erro ao excluir compromisso');
            }
            
        } catch (error) {
            console.error('Erro ao excluir compromisso:', error);
            alert('Erro ao excluir compromisso');
        }
    },
    
    abrirModal() {
        document.getElementById('compromissoModal').classList.remove('hidden');
    },
    
    fecharModal() {
        document.getElementById('compromissoModal').classList.add('hidden');
        document.getElementById('compromissoForm').reset();
        document.getElementById('compromissoId').value = '';
        document.getElementById('modalTitle').textContent = 'Novo Compromisso';
        document.getElementById('deleteBtn').classList.add('hidden');
        this.compromissoAtual = null;
    },
    
    getCsrfToken() {
        // Obter CSRF token dos cookies
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
};

// Inicializar quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
    calendario.init();
});
