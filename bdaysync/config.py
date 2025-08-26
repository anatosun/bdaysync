"""
Configuration management and environment validation
"""

import os
import logging

def setup_logging():
    """Setup logging configuration from environment variables"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_to_file = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
    debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
    
    if debug_mode:
        log_level = 'DEBUG'
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Setup handlers
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(simple_formatter)
    handlers.append(console_handler)
    
    # File handler (if enabled)
    if log_to_file:
        try:
            os.makedirs('/var/log/birthday-sync', exist_ok=True)
            file_handler = logging.FileHandler('/var/log/birthday-sync/sync.log')
            file_handler.setFormatter(detailed_formatter)
            handlers.append(file_handler)
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not create log file: {e}")
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=handlers
    )
    
    # Suppress some noisy third-party loggers unless in debug mode
    if not debug_mode:
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

def validate_environment():
    """Validate required environment variables"""
    logger = logging.getLogger(__name__)
    
    required_vars = [
        'CARDAV_SERVER_URL',
        'CARDAV_USERNAME', 
        'CARDAV_PASSWORD',
        'CALDAV_SERVER_URL',
        'CALDAV_USERNAME',
        'CALDAV_PASSWORD'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    logger.info("Environment validation passed")
    return True

def get_birthday_config():
    """Get birthday event configuration from environment"""
    return {
        'event_title_template': os.getenv('BIRTHDAY_EVENT_TITLE', '🎂 {name}\'s Birthday'),
        'event_description_template': os.getenv('BIRTHDAY_EVENT_DESCRIPTION', 'Birthday of {name}'),
        'reminder_days_str': os.getenv('BIRTHDAY_REMINDER_DAYS', '1'),
        'reminder_template': os.getenv('BIRTHDAY_REMINDER_MESSAGE', 'Reminder: {name}\'s birthday is in {days} days!'),
        'event_category': os.getenv('BIRTHDAY_EVENT_CATEGORY', 'Birthday'),
        'update_existing': os.getenv('BIRTHDAY_UPDATE_EXISTING', 'true').lower() == 'true'
    }

def get_scheduler_config():
    """Get scheduler configuration from environment"""
    return {
        'sync_schedule': os.getenv('SYNC_SCHEDULE', '0 6 * * *'),
        'diagnostic_schedule': os.getenv('DIAGNOSTIC_SCHEDULE', '0 7 * * 0'),
        'sync_interval_hours': int(os.getenv('SYNC_INTERVAL_HOURS', '0')),
        'startup_delay': int(os.getenv('STARTUP_DELAY', '30'))
    }
