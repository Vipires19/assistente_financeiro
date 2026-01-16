"""
Configuração e conexão com MongoDB.

Este módulo centraliza a conexão com MongoDB para uso em todos os repositories.
Localização: core/database.py

Uso:
    from core.database import get_database
    
    db = get_database()
    collection = db['minha_collection']
"""
from pymongo import MongoClient
from django.conf import settings
from typing import Optional


_client: Optional[MongoClient] = None
_database = None


def get_client() -> MongoClient:
    """
    Retorna o cliente MongoDB (singleton).
    
    Returns:
        MongoClient instance
    """
    global _client
    
    if _client is None:
        mongodb_config = settings.MONGODB_SETTINGS
        
        # Monta a URI de conexão
        host = mongodb_config['URI']
        username = mongodb_config.get('username', '')
        password = mongodb_config.get('password', '')
        
        if username and password:
            # Remove protocolo do host se presente
            host_clean = host.replace('mongodb://', '').replace('mongodb+srv://', '')
            if 'mongodb+srv://' in host:
                uri = f"mongodb+srv://{username}:{password}@{host_clean}"
            else:
                uri = f"mongodb://{username}:{password}@{host_clean}"
        else:
            uri = host
        
        options = mongodb_config.get('options', {})
        _client = MongoClient(uri, **options)
        
        # Testa a conexão
        try:
            _client.admin.command('ping')
        except Exception as e:
            raise ConnectionError(f"Erro ao conectar ao MongoDB: {e}")
    
    return _client


def get_database():
    """
    Retorna o banco de dados MongoDB.
    
    Returns:
        Database instance
    """
    global _database
    
    if _database is None:
        client = get_client()
        _database = client[settings.MONGODB_SETTINGS['DB_NAME']]
    
    return _database


def close_connection():
    """Fecha a conexão com MongoDB."""
    global _client, _database
    
    if _client:
        _client.close()
        _client = None
        _database = None

