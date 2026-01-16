"""
Repository para operações de usuário no MongoDB.

Localização: core/repositories/user_repository.py

Encapsula todas as operações com a collection 'users' no MongoDB.
"""
from typing import Optional, Dict, Any
from core.repositories.base_repository import BaseRepository
from core.database import get_database
import bcrypt
from datetime import datetime


class UserRepository(BaseRepository):
    """
    Repository para gerenciar usuários no MongoDB.
    
    Exemplo de uso:
        repo = UserRepository()
        user = repo.create('user@email.com', 'senha123')
    """
    
    def __init__(self):
        super().__init__('users')
    
    def _ensure_indexes(self):
        """Cria índices necessários."""
        self.collection.create_index('email', unique=True)
    
    def create(self, email: str, password: str, role: str = 'user',
              account_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Cria um novo usuário.
        
        Args:
            email: Email do usuário
            password: Senha em texto plano (será hasheada)
            role: Role do usuário ('user' ou 'admin', default: 'user')
            account_id: ID da conta/organização (opcional, futuro)
            **kwargs: Campos adicionais do usuário
        
        Returns:
            Dict com os dados do usuário criado (sem password_hash)
        """
        # Hash da senha com bcrypt
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')
        
        # Valida role
        valid_roles = ['user', 'admin']
        if role not in valid_roles:
            role = 'user'
        
        # Categorias pré-definidas - sempre populadas ao criar usuário
        from finance.models.categoria_model import CategoriaModel
        categorias_predefinidas = CategoriaModel.get_categorias_predefinidas()
        
        user_data = {
            'email': email.lower().strip(),
            'password_hash': hashed_password,
            'role': role,
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            **kwargs
        }
        
        # Se categorias já vierem em kwargs, usa elas (permite sobrescrever)
        # Caso contrário, popula com categorias pré-definidas
        if 'categorias' not in kwargs or not kwargs.get('categorias'):
            user_data['categorias'] = categorias_predefinidas
        else:
            user_data['categorias'] = kwargs['categorias']
        
        # Adiciona account_id se fornecido (futuro)
        if account_id:
            from bson import ObjectId
            user_data['account_id'] = ObjectId(account_id) if isinstance(account_id, str) else account_id
        
        # GARANTIA FINAL: Verifica se categorias foram populadas antes de salvar
        # Se por algum motivo o campo categorias estiver vazio ou None, popula novamente
        if 'categorias' not in user_data or not user_data.get('categorias'):
            user_data['categorias'] = CategoriaModel.get_categorias_predefinidas()
        
        # Salva o usuário no MongoDB
        result = self.collection.insert_one(user_data)
        user_data['_id'] = result.inserted_id
        
        # Remove senha do retorno
        user_data.pop('password_hash', None)
        return user_data
    
    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Busca usuário por email.
        
        Args:
            email: Email do usuário
        
        Returns:
            Dict com dados do usuário ou None
        """
        return self.collection.find_one({'email': email.lower().strip()})
    
    def find_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca usuário por ID.
        
        Args:
            user_id: ID do usuário (ObjectId como string)
        
        Returns:
            Dict com dados do usuário ou None (sem password_hash)
        """
        from bson import ObjectId
        try:
            user = self.collection.find_one({'_id': ObjectId(user_id)})
            if user:
                user.pop('password_hash', None)  # Remove senha do retorno
            return user
        except:
            return None
    
    def verify_password(self, email: str, password: str) -> bool:
        """
        Verifica se a senha está correta.
        
        Args:
            email: Email do usuário
            password: Senha em texto plano
        
        Returns:
            True se a senha estiver correta, False caso contrário
        """
        user = self.find_by_email(email)
        if not user or 'password_hash' not in user:
            return False
        
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                user['password_hash'].encode('utf-8')
            )
        except:
            return False
    
    def update(self, user_id: str, **kwargs) -> bool:
        """
        Atualiza dados do usuário.
        
        Args:
            user_id: ID do usuário
            **kwargs: Campos a atualizar
        
        Returns:
            True se atualizado com sucesso
        """
        from bson import ObjectId
        
        kwargs['updated_at'] = datetime.utcnow()
        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': kwargs}
        )
        return result.modified_count > 0

