"""
CalDAV client for creating birthday events
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import vobject
import caldav
from config import get_birthday_config

logger = logging.getLogger(__name__)

class CalDAVClient:
    """Client for creating events in CalDAV server"""
    
    def __init__(self, server_url: str, username: str, password: str):
        try:
            self.client = caldav.DAVClient(
                url=server_url,
                username=username,
                password=password
            )
            self.principal = self.client.principal()
            self.calendars = self.principal.calendars()
            
            if not self.calendars:
                raise Exception("No calendars found")
                
            # Use first calendar by default
            self.calendar = self.calendars[0]
            logger.info(f"Using calendar: {self.calendar.name}")
            
            # Load configuration from environment variables
            self._load_config()
            
        except Exception as e:
            logger.error(f"Error connecting to CalDAV server: {e}")
            raise
    
    def _load_config(self):
        """Load configuration from environment variables"""
        config = get_birthday_config()
        
        self.event_title_template = config['event_title_template']
        self.event_description_template = config['event_description_template']
        
        # Parse reminder days
        try:
            self.reminder_days = [int(d.strip()) for d in config['reminder_days_str'].split(',') if d.strip()]
        except ValueError:
            logger.warning(f"Invalid reminder days format: {config['reminder_days_str']}, using default: [1]")
            self.reminder_days = [1]
        
        self.reminder_template = config['reminder_template']
        self.event_category = config['event_category']
        self.update_existing = config['update_existing']
        
        logger.info("Birthday event configuration:")
        logger.info(f"  Title template: {self.event_title_template}")
        logger.info(f"  Description template: {self.event_description_template}")
        logger.info(f"  Reminder days: {self.reminder_days}")
        logger.info(f"  Reminder message: {self.reminder_template}")
        logger.info(f"  Category: {self.event_category}")
        logger.info(f"  Update existing: {self.update_existing}")
    
    def create_birthday_event(self, contact: Dict, year: int = None) -> bool:
        """Create a birthday event for a contact"""
        try:
            if year is None:
                year = datetime.now().year
            
            birthday = contact['birthday']
            name = contact['name']
            
            # Create event date for this year
            event_date = birthday.replace(year=year)
            
            # Generate event details from templates
            event_title = self.event_title_template.format(name=name)
            event_description = self.event_description_template.format(name=name)
            
            # Check if event already exists
            existing_event = self._find_existing_event(name, event_date)
            if existing_event:
                if self.update_existing:
                    return self._update_existing_event(existing_event, contact, year, event_title, event_description)
                else:
                    logger.info(f"Birthday event for {name} on {event_date} already exists (skipping update)")
                    return False
            
            # Create unique UID
            event_uid = f"birthday-{name.replace(' ', '-').lower()}-{event_date.strftime('%Y%m%d')}"
            
            # Create iCalendar event
            cal = vobject.iCalendar()
            
            # Add event
            event = cal.add('vevent')
            event.add('uid').value = event_uid
            event.add('dtstart').value = event_date
            event.add('dtend').value = event_date + timedelta(days=1)
            event.add('summary').value = event_title
            event.add('description').value = event_description
            event.add('categories').value = [self.event_category]
            
            # Make it an all-day event
            event.dtstart.params['VALUE'] = 'DATE'
            event.dtend.params['VALUE'] = 'DATE'
            
            # Add yearly recurrence
            event.add('rrule').value = 'FREQ=YEARLY'
            
            # Add reminders
            for days_before in self.reminder_days:
                alarm = event.add('valarm')
                alarm.add('action').value = 'DISPLAY'
                alarm.add('trigger').value = timedelta(days=-days_before)
                
                # Generate reminder message
                reminder_message = self._format_reminder_message(name, days_before)
                alarm.add('description').value = reminder_message
            
            # Save to CalDAV server
            self.calendar.save_event(cal.serialize())
            logger.info(f"Created birthday event for {name} on {event_date}")
            logger.info(f"  Title: {event_title}")
            logger.info(f"  Reminders: {len(self.reminder_days)} reminder(s) {self.reminder_days} days before")
            return True
            
        except Exception as e:
            logger.error(f"Error creating birthday event for {contact.get('name', 'unknown')}: {e}")
            return False
    
    def _format_reminder_message(self, name: str, days_before: int) -> str:
        """Format the reminder message based on template"""
        try:
            if days_before == 0:
                # Special handling for "today"
                if '{days}' in self.reminder_template:
                    message = self.reminder_template.format(name=name, days=days_before)
                    # Replace common patterns with "today"
                    message = message.replace('in 0 days', 'today')
                    message = message.replace('in 0 day', 'today')
                    message = message.replace('is in today', 'is today')
                    return message
                else:
                    return f"Today is {name}'s birthday!"
            elif days_before == 1:
                message = self.reminder_template.format(name=name, days=days_before)
                # Fix pluralization for 1 day
                message = message.replace('1 days', '1 day')
                return message
            else:
                return self.reminder_template.format(name=name, days=days_before)
        except (KeyError, ValueError, AttributeError) as e:
            logger.warning(f"Error formatting reminder message with template '{self.reminder_template}': {e}, using simple format")
            
            # Fallback to simple, safe messages
            if days_before == 0:
                return f"Today is {name}'s birthday!"
            elif days_before == 1:
                return f"Tomorrow is {name}'s birthday!"
            else:
                return f"{name}'s birthday is in {days_before} days!"
    
    def _find_existing_event(self, name: str, date) -> Optional:
        """Find existing birthday event for a contact"""
        try:
            # Use the new calendar.search method instead of deprecated date_search
            search_xml = f'''
            <c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
                <d:prop>
                    <d:getetag/>
                    <c:calendar-data/>
                </d:prop>
                <c:filter>
                    <c:comp-filter name="VCALENDAR">
                        <c:comp-filter name="VEVENT">
                            <c:time-range start="{date.strftime('%Y%m%d')}T000000Z" 
                                         end="{(date + timedelta(days=1)).strftime('%Y%m%d')}T000000Z"/>
                        </c:comp-filter>
                    </c:comp-filter>
                </c:filter>
            </c:calendar-query>'''
            
            events = self.calendar.search(search_xml)
            
            for event in events:
                try:
                    cal = vobject.readOne(event.data)
                    if hasattr(cal.vevent, 'summary'):
                        summary = cal.vevent.summary.value
                        # Check if this event is for this person (name appears in summary)
                        if name in summary and (self.event_category.lower() in summary.lower() or 'birthday' in summary.lower()):
                            return event
                        # Also check by UID pattern
                        if hasattr(cal.vevent, 'uid'):
                            uid = cal.vevent.uid.value
                            expected_uid = f"birthday-{name.replace(' ', '-').lower()}"
                            if uid.startswith(expected_uid):
                                return event
                except Exception as e:
                    logger.debug(f"Error parsing existing event: {e}")
                    continue
            return None
            
        except Exception as e:
            logger.debug(f"Error searching for existing events with new method: {e}")
            
            # Fallback to deprecated method if available
            try:
                logger.debug("Falling back to deprecated date_search method")
                events = self.calendar.date_search(date, date + timedelta(days=1))
                
                for event in events:
                    try:
                        cal = vobject.readOne(event.data)
                        if hasattr(cal.vevent, 'summary'):
                            summary = cal.vevent.summary.value
                            if name in summary and (self.event_category.lower() in summary.lower() or 'birthday' in summary.lower()):
                                return event
                            if hasattr(cal.vevent, 'uid'):
                                uid = cal.vevent.uid.value
                                expected_uid = f"birthday-{name.replace(' ', '-').lower()}"
                                if uid.startswith(expected_uid):
                                    return event
                    except Exception as e:
                        logger.debug(f"Error parsing existing event in fallback: {e}")
                        continue
                return None
                
            except Exception as fallback_e:
                logger.warning(f"Both new and fallback search methods failed: {fallback_e}")
                return None
    
    def _update_existing_event(self, existing_event, contact: Dict, year: int, new_title: str, new_description: str) -> bool:
        """Update an existing birthday event with new templates"""
        try:
            name = contact['name']
            event_date = contact['birthday'].replace(year=year)
            
            # Parse existing event
            cal = vobject.readOne(existing_event.data)
            event = cal.vevent
            
            # Check if update is needed
            current_title = event.summary.value if hasattr(event, 'summary') else ''
            current_description = event.description.value if hasattr(event, 'description') else ''
            
            if current_title == new_title and current_description == new_description:
                # Check reminders too
                current_reminders = []
                if hasattr(event, 'valarm_list'):
                    for alarm in event.valarm_list:
                        if hasattr(alarm, 'trigger'):
                            trigger = alarm.trigger.value
                            if isinstance(trigger, timedelta):
                                days = abs(trigger.days)
                                current_reminders.append(days)
                
                current_reminders.sort()
                expected_reminders = sorted(self.reminder_days)
                
                if current_reminders == expected_reminders:
                    logger.debug(f"No update needed for {name}'s birthday event")
                    return False
            
            logger.info(f"Updating birthday event for {name} on {event_date}")
            logger.info(f"  Old title: {current_title}")
            logger.info(f"  New title: {new_title}")
            
            # Update event properties
            if hasattr(event, 'summary'):
                event.summary.value = new_title
            else:
                event.add('summary').value = new_title
                
            if hasattr(event, 'description'):
                event.description.value = new_description
            else:
                event.add('description').value = new_description
            
            # Update category
            if hasattr(event, 'categories'):
                event.categories.value = [self.event_category]
            else:
                event.add('categories').value = [self.event_category]
            
            # Remove old alarms and add new ones
            if hasattr(event, 'valarm_list'):
                for alarm in list(event.valarm_list):
                    event.remove(alarm)
            
            # Add new reminders
            for days_before in self.reminder_days:
                alarm = event.add('valarm')
                alarm.add('action').value = 'DISPLAY'
                alarm.add('trigger').value = timedelta(days=-days_before)
                reminder_message = self._format_reminder_message(name, days_before)
                alarm.add('description').value = reminder_message
            
            # Save updated event
            existing_event.data = cal.serialize()
            existing_event.save()
            
            logger.info(f"Updated birthday event for {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating birthday event for {contact.get('name', 'unknown')}: {e}")
            return False
