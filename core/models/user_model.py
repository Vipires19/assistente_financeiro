"""
Modelo de usuário com suporte a roles e accounts (futuro).

Localização: core/models/user_model.py

Este módulo define a estrutura de dados do usuário no MongoDB,
incluindo suporte para roles e accounts (preparado para futuro).
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId


class UserModel:
    """
    Modelo de usuário com suporte a roles e accounts.
    
    Schema no MongoDB:
    {
      _id: ObjectId,
      email: String (único),
      password_hash: String,
      role: String,              // 'user', 'admin' (futuro: mais roles)
      account_id: ObjectId,      // ID da conta/organização (futuro)
      is_active: Boolean,
      aceitou_termos: Boolean,
      data_aceite_termos: ISODate,
      versao_termos: String,     // ex: "1.0"
      created_at: ISODate,
      updated_at: ISODate
    }
    """
    
    # Roles disponíveis
    ROLE_USER = 'user'
    ROLE_ADMIN = 'admin'
    
    # Roles válidas
    VALID_ROLES = [ROLE_USER, ROLE_ADMIN]
    
    @staticmethod
    def create_user_data(email: str, password_hash: str, 
                        role: str = ROLE_USER,
                        account_id: Optional[str] = None,
                        **kwargs) -> Dict[str, Any]:
        """
        Cria estrutura de dados do usuário.
        
        Args:
            email: Email do usuário
            password_hash: Hash da senha
            role: Role do usuário (default: 'user')
            account_id: ID da conta/organização (opcional, futuro)
            **kwargs: Campos adicionais
        
        Returns:
            Dict com dados do usuário
        """
        if role not in UserModel.VALID_ROLES:
            role = UserModel.ROLE_USER
        
        user_data = {
            'email': email.lower().strip(),
            'password_hash': password_hash,
            'role': role,
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            **kwargs
        }
        
        # Adiciona account_id se fornecido (futuro)
        if account_id:
            user_data['account_id'] = ObjectId(account_id) if isinstance(account_id, str) else account_id
        
        return user_data
    
    @staticmethod
    def has_permission(user: Dict[str, Any], permission: str) -> bool:
        """
        Verifica se usuário tem permissão.
        
        Args:
            user: Dict com dados do usuário
            permission: Permissão a verificar
        
        Returns:
            True se usuário tem permissão
        """
        role = user.get('role', UserModel.ROLE_USER)
        
        # Admin tem todas as permissões
        if role == UserModel.ROLE_ADMIN:
            return True
        
        # Permissões específicas por role (futuro)
        permissions_map = {
            UserModel.ROLE_USER: ['view_own_data', 'create_transaction', 'generate_report'],
            UserModel.ROLE_ADMIN: ['*']  # Todas
        }
        
        user_permissions = permissions_map.get(role, [])
        return '*' in user_permissions or permission in user_permissions
    
    @staticmethod
    def is_admin(user: Dict[str, Any]) -> bool:
        """
        Verifica se usuário é admin.
        
        Args:
            user: Dict com dados do usuário
        
        Returns:
            True se usuário é admin
        """
        return user.get('role') == UserModel.ROLE_ADMIN

