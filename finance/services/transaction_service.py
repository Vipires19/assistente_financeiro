"""
Service para lógica de transações financeiras.

Localização: finance/services/transaction_service.py

Este service contém a lógica de negócio relacionada a transações.
Ele usa o TransactionRepository para acessar dados, mas adiciona
validações e regras de negócio.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from finance.repositories.transaction_repository import TransactionRepository
from core.services.audit_log_service import AuditLogService
from bson import ObjectId


class TransactionService:
    """
    Service para gerenciar transações financeiras.
    
    Exemplo de uso:
        service = TransactionService()
        transaction = service.create_transaction(
            user_id='...',
            amount=100.50,
            description='Compra',
            transaction_type='expense'
        )
    """
    
    def __init__(self):
        self.transaction_repo = TransactionRepository()
        self.audit_service = AuditLogService()
    
    def create_transaction(self, user_id: str, amount: float, 
                          description: str, transaction_type: str,
                          category: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Cria uma nova transação.
        
        Args:
            user_id: ID do usuário
            amount: Valor da transação
            description: Descrição
            transaction_type: 'income' ou 'expense'
            category: Categoria (opcional)
            **kwargs: Campos adicionais
        
        Returns:
            Dict com dados da transação criada
        
        Raises:
            ValueError: Se dados inválidos
        """
        # Validações de negócio
        if transaction_type not in ['income', 'expense']:
            raise ValueError("Tipo deve ser 'income' ou 'expense'")
        
        if not description or not description.strip():
            raise ValueError("Descrição é obrigatória")
        
        if amount <= 0:
            raise ValueError("Valor deve ser maior que zero")
        
        # Prepara dados para inserção conforme schema
        created_at = kwargs.get('created_at', kwargs.get('date', datetime.utcnow()))
        
        transaction_data = {
            'user_id': ObjectId(user_id),
            'type': transaction_type,
            'category': (category or 'outros').strip(),
            'description': description.strip(),
            'value': abs(float(amount)),  # Sempre positivo conforme schema
            'created_at': created_at,
            'hour': created_at.hour if isinstance(created_at, datetime) else datetime.utcnow().hour,
            **{k: v for k, v in kwargs.items() if k not in ['date', 'created_at']}
        }
        
        # Usa repository para persistir
        return self.transaction_repo.create(transaction_data)
    
    def get_user_transactions(self, user_id: str, limit: int = 100,
                             skip: int = 0) -> List[Dict[str, Any]]:
        """
        Busca transações do usuário.
        
        Args:
            user_id: ID do usuário
            limit: Limite de resultados
            skip: Quantidade a pular
        
        Returns:
            Lista de transações
        """
        return self.transaction_repo.find_by_user(user_id, limit, skip)
    
    def get_financial_summary(self, user_id: str, 
                             start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calcula resumo financeiro do usuário.
        
        Args:
            user_id: ID do usuário
            start_date: Data inicial (opcional)
            end_date: Data final (opcional)
        
        Returns:
            Dict com resumo financeiro
        """
        return self.transaction_repo.get_summary(user_id, start_date, end_date)
    
    def delete_transaction(self, transaction_id: str, user_id: str) -> bool:
        """
        Deleta uma transação.
        
        SEGURANÇA: Valida que a transação pertence ao usuário antes de deletar.
        
        Args:
            transaction_id: ID da transação
            user_id: ID do usuário (obrigatório)
        
        Returns:
            True se deletado com sucesso
        
        Raises:
            ValueError: Se transação não encontrada ou não pertence ao usuário
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        
        # Busca transação validando user_id (segurança)
        transaction = self.transaction_repo.find_by_id(transaction_id, user_id=user_id)
        
        if not transaction:
            # Não revela se transação existe ou não (segurança)
            raise ValueError("Transação não encontrada ou não pertence ao usuário")
        
        # Validação adicional de segurança
        if str(transaction['user_id']) != user_id:
            raise ValueError("Transação não pertence ao usuário")
        
        return self.transaction_repo.delete(transaction_id)

