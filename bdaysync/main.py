#!/usr/bin/env python3
"""
CardDAV to CalDAV Birthday Sync
Main entry point with scheduling and argument parsing
"""

import os
import sys
import logging
import argparse
from datetime import datetime

from cardav_client import CardDAVClient
from caldav_client import CalDAVClient
from scheduler import SchedulerService
from config import setup_logging, validate_environment

# ASCII Art Banner
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ██████╗  █████╗ ██╗   ██╗    ███████╗██╗   ██╗    ║
║   ██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝    ██╔════╝╚██╗ ██╔╝    ║
║   ██████╔╝██║  ██║███████║ ╚████╔╝     ███████╗ ╚████╔╝     ║
║   ██╔══██╗██║  ██║██╔══██║  ╚██╔╝      ╚════██║  ╚██╔╝      ║
║   ██████╔╝██████╔╝██║  ██║   ██║       ███████║   ██║       ║
║   ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝       ╚══════╝   ╚═╝       ║
║                                                              ║
║              🎂 Birthday Sync Service 🎂                     ║
║         CardDAV to CalDAV Birthday Synchronization           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

def print_banner():
    """Print the ASCII art banner"""
    print(BANNER)
    print(f"Version: {os.getenv('VERSION', '1.0.0')}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("─" * 62)
    print()

def diagnose_cardav():
    """Diagnostic function to test CardDAV connectivity"""
    cardav_url = os.getenv('CARDAV_SERVER_URL')
    cardav_username = os.getenv('CARDAV_USERNAME')
    cardav_password = os.getenv('CARDAV_PASSWORD')
    
    if not all([cardav_url, cardav_username, cardav_password]):
        print("Missing CardDAV environment variables")
        return False
    
    print(f"Testing CardDAV connectivity and addressbook discovery:")
    print(f"Base URL: {cardav_url}")
    print(f"Username: {cardav_username}")
    print("-" * 60)
    
    try:
        # Test the discovery approach
        client = CardDAVClient(cardav_url, cardav_username, cardav_password)
        print(f"✓ Authentication successful!")
        print(f"✓ Found {len(client.addressbook_urls)} addressbooks:")
        for i, ab_url in enumerate(client.addressbook_urls, 1):
            print(f"  {i}. {ab_url}")
            
        # Test fetching contacts
        contacts = client.get_contacts()
        print(f"✓ Total contacts with birthdays: {len(contacts)}")
        
        for contact in contacts:
            ab_name = contact.get('addressbook', 'unknown').split('/')[-1] or contact.get('addressbook', 'unknown').split('/')[-2]
            print(f"  - {contact['name']} ({contact['birthday']}) from '{ab_name}'")
        
        return True
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main_sync():
    """Main sync function"""
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize clients
        logger.info("Connecting to CardDAV server...")
        cardav_client = CardDAVClient(
            os.getenv('CARDAV_SERVER_URL'),
            os.getenv('CARDAV_USERNAME'),
            os.getenv('CARDAV_PASSWORD')
        )
        
        logger.info("Connecting to CalDAV server...")
        caldav_client = CalDAVClient(
            os.getenv('CALDAV_SERVER_URL'),
            os.getenv('CALDAV_USERNAME'),
            os.getenv('CALDAV_PASSWORD')
        )
        
        # Fetch contacts with birthdays
        logger.info("Fetching contacts from CardDAV server...")
        contacts = cardav_client.get_contacts()
        
        if not contacts:
            logger.warning("No contacts with birthdays found")
            return False
        
        logger.info(f"Found {len(contacts)} contacts with birthdays")
        
        # Create birthday events
        created_count = 0
        current_year = datetime.now().year
        
        for contact in contacts:
            logger.info(f"Processing birthday for: {contact['name']} ({contact['birthday']})")
            if caldav_client.create_birthday_event(contact, current_year):
                created_count += 1
            
            # Also create for next year
            if caldav_client.create_birthday_event(contact, current_year + 1):
                created_count += 1
        
        logger.info(f"Successfully created {created_count} birthday events")
        return True
        
    except Exception as e:
        logger.error(f"Error in main sync execution: {e}")
        if os.getenv('DEBUG', 'false').lower() == 'true':
            import traceback
            logger.error(traceback.format_exc())
        return False

def health_check():
    """Health check function"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Performing health check...")
        
        # Check if we can import required modules
        import vobject
        import caldav
        import requests
        
        # Check environment variables
        if not validate_environment():
            return False
        
        # Optional: Test connectivity (can be slow)
        if os.getenv('HEALTH_CHECK_CONNECTIVITY', 'false').lower() == 'true':
            logger.info("Testing connectivity as part of health check...")
            return diagnose_cardav()
        
        logger.info("Health check passed")
        return True
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(description='Birthday sync service')
    parser.add_argument('--diagnose', action='store_true', help='Run diagnostics')
    parser.add_argument('--health-check', action='store_true', help='Run health check')
    parser.add_argument('--once', action='store_true', help='Run sync once and exit')
    parser.add_argument('--no-banner', action='store_true', help='Skip ASCII art banner')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Print banner unless suppressed
    if not args.no_banner:
        print_banner()
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Handle special commands
    if args.health_check:
        success = health_check()
        sys.exit(0 if success else 1)
    
    if args.diagnose:
        success = diagnose_cardav()
        sys.exit(0 if success else 1)
    
    # Check run mode from environment
    run_mode = os.getenv('RUN_MODE', 'daemon').lower()
    
    if args.once or run_mode == 'once':
        logger.info("Running single sync operation...")
        success = main_sync()
        sys.exit(0 if success else 1)
    elif run_mode == 'daemon':
        scheduler = SchedulerService(main_sync, diagnose_cardav)
        try:
            scheduler.run_daemon()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        sys.exit(0)
    else:
        # Default: run the sync once
        logger.info("Running sync operation (default mode)...")
        success = main_sync()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
