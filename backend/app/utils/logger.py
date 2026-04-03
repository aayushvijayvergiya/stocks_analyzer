from pythonjsonlogger.json import JsonFormatter as BaseJsonFormatter
import logging
from contextvars import ContextVar
from typing import Optional
from app.config import settings

# Context variable to store request_id
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

class JsonFormatter(BaseJsonFormatter):
    def add_fields(self, log_data, record, message_dict):
        super().add_fields(log_data, record, message_dict)
        log_data['timestamp'] = self.formatTime(record, self.datefmt)
        log_data['level'] = record.levelname
        log_data['message'] = record.getMessage()
        log_data['module'] = record.module
        log_data['logger'] = record.name
        
        # Add request_id if available
        request_id = request_id_var.get()
        if request_id:
            log_data['request_id'] = request_id

def get_logger(name: str) -> logging.Logger:
    """
    Factory function to create and configure a logger with JSON formatting.
    
    Args:
        name: Name of the logger (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set log level based on environment
    if settings.ENVIRONMENT.lower() == 'development':
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Avoid adding multiple handlers if logger already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = JsonFormatter('%(timestamp)s %(level)s %(message)s %(module)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

# Default logger instance
logger = get_logger("stocks_analyzer_backend")
