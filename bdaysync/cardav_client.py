"""
CardDAV client for fetching contacts with birthdays
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
from xml.etree import ElementTree
import vobject
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class CardDAVClient:
    """Client for reading contacts from CardDAV server"""

    def __init__(self, server_url: str, username: str, password: str):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        
        # Try both Basic and Digest auth
        self.basic_auth = HTTPBasicAuth(username, password)
        self.digest_auth = HTTPDigestAuth(username, password)
        self.auth = None  # Will be set after testing
        
        # Discover addressbooks
        self.addressbook_urls = []
        self._test_auth_and_discover()
    
    def _test_auth_and_discover(self):
        """Test authentication and discover all addressbooks at the given URL"""
        logger.info(f"Testing authentication and discovering addressbooks at: {self.server_url}")
        logger.info(f"Username: {self.username}")
        
        try:
            # Test Basic auth first
            headers = {
                'Content-Type': 'application/xml; charset=utf-8',
                'Depth': '1',
            }
            propfind_body = '''<?xml version="1.0" encoding="utf-8"?>
            <D:propfind xmlns:D="DAV:">
                <D:prop>
                    <D:resourcetype />
                </D:prop>
            </D:propfind>'''
            response = requests.request('PROPFIND', self.server_url, 
                                      auth=self.basic_auth, headers=headers,
                                      data=propfind_body, timeout=10)
            logger.info(f"Basic auth response: {response.status_code}")
            
            if response.status_code in [200, 207]:
                logger.info("Basic authentication successful!")
                self.auth = self.basic_auth
            elif response.status_code == 401:
                # Try Digest auth
                logger.info("Basic auth failed, trying Digest authentication...")
                response = requests.request('PROPFIND', self.server_url, 
                                          auth=self.digest_auth, headers=headers,
                                          data=propfind_body, timeout=10)
                logger.info(f"Digest auth response: {response.status_code}")
                
                if response.status_code in [200, 207]:
                    logger.info("Digest authentication successful!")
                    self.auth = self.digest_auth
                else:
                    raise Exception(f"Authentication failed: {response.status_code}")
            else:
                raise Exception(f"Authentication failed: {response.status_code}")
            
            # Now discover addressbooks from the response
            logger.debug(f"Discovery response: {response.text[:1000]}...")
            self.addressbook_urls = self._extract_addressbooks(response.text)
            
            if not self.addressbook_urls:
                raise Exception("No addressbooks found at the provided URL")
            
            logger.info(f"Discovered {len(self.addressbook_urls)} addressbooks:")
            for ab_url in self.addressbook_urls:
                logger.info(f"  - {ab_url}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error during authentication and discovery: {e}")
            raise
    
    def _extract_addressbooks(self, xml_response: str) -> List[str]:
        """Extract addressbook collection URLs from PROPFIND response"""
        return self._find_addressbooks(xml_response)

    def _find_addressbooks(self, xml_response: str) -> List[str]:
        """Find CardDAV addressbook collections in a DAV multistatus response."""
        dav_namespace = 'DAV:'
        carddav_namespace = 'urn:ietf:params:xml:ns:carddav'

        try:
            root = ElementTree.fromstring(xml_response)
        except ElementTree.ParseError as error:
            logger.warning(f"Could not parse CardDAV discovery XML: {error}")
            return []

        addressbooks = []
        for response in root.findall(f'{{{dav_namespace}}}response'):
            href = response.findtext(f'{{{dav_namespace}}}href')
            if not href:
                continue

            has_addressbook_type = False
            for propstat in response.findall(f'{{{dav_namespace}}}propstat'):
                status = propstat.findtext(f'{{{dav_namespace}}}status', '')
                if not status.startswith('HTTP/') or ' 2' not in status:
                    continue

                resource_type = propstat.find(f'{{{dav_namespace}}}prop/{{{dav_namespace}}}resourcetype')
                if resource_type is not None and resource_type.find(f'{{{carddav_namespace}}}addressbook') is not None:
                    has_addressbook_type = True
                    break

            href = href.strip()
            logger.debug(f"Found href: {href}")
            if has_addressbook_type:
                full_url = self._resolve_url(href)
                if full_url not in addressbooks:
                    addressbooks.append(full_url)
                    logger.debug(f"Found addressbook: {full_url}")

        return addressbooks

    def get_contacts(self) -> List[Dict]:
        """Fetch all contacts from all discovered addressbooks"""
        all_contacts = []
        
        for addressbook_url in self.addressbook_urls:
            logger.info(f"Processing addressbook: {addressbook_url}")
            contacts = self._get_contacts_from_addressbook(addressbook_url)
            all_contacts.extend(contacts)
            logger.info(f"Found {len(contacts)} contacts with birthdays in this addressbook")
        
        logger.info(f"Total contacts with birthdays across all addressbooks: {len(all_contacts)}")
        return all_contacts
    
    def _get_contacts_from_addressbook(self, addressbook_url: str) -> List[Dict]:
        """Fetch contacts from a specific addressbook"""
        contacts = []
        
        try:
            # Simple PROPFIND to get all resources in this addressbook
            headers = {
                'Content-Type': 'application/xml; charset=utf-8',
                'Depth': '1'
            }
            
            propfind_body = '''<?xml version="1.0" encoding="utf-8" ?>
            <D:propfind xmlns:D="DAV:">
                <D:prop>
                    <D:getcontenttype />
                </D:prop>
            </D:propfind>'''
            
            logger.debug(f"Discovering resources in addressbook: {addressbook_url}")
            response = requests.request('PROPFIND', addressbook_url, 
                                      auth=self.auth, headers=headers, data=propfind_body)
            
            logger.debug(f"PROPFIND response status: {response.status_code}")
            
            if response.status_code in [200, 207]:
                logger.debug(f"Raw XML response preview: {response.text[:500]}...")
                
                # Parse the response to find vCard resources
                vcard_urls = self._extract_vcard_urls(response.text)
                logger.info(f"Found {len(vcard_urls)} vCard resources in {addressbook_url}")
                
                if not vcard_urls:
                    logger.debug("No vCard URLs found in this addressbook")
                    return contacts
                
                # Fetch each vCard
                for i, vcard_url in enumerate(vcard_urls):
                    try:
                        full_url = self._resolve_url(vcard_url)
                        logger.debug(f"Fetching vCard {i+1}/{len(vcard_urls)} from: {full_url}")
                        
                        vcard_response = requests.get(full_url, auth=self.auth, timeout=10)
                        logger.debug(f"vCard response status: {vcard_response.status_code}")
                        
                        if vcard_response.status_code == 200:
                            logger.debug(f"vCard content preview: {vcard_response.text[:200]}...")
                            contact = self._parse_vcard(vcard_response.text)
                            if contact:
                                contact['addressbook'] = addressbook_url
                                contacts.append(contact)
                                logger.info(f"✓ Parsed contact: {contact['name']} (Birthday: {contact.get('birthday', 'None')}) from {addressbook_url}")
                            else:
                                logger.debug(f"No birthday found in vCard: {vcard_url}")
                        else:
                            logger.warning(f"Failed to fetch vCard {vcard_url}: {vcard_response.status_code}")
                    except Exception as e:
                        logger.warning(f"Error processing vCard {vcard_url}: {e}")
                        continue
            else:
                logger.error(f"Failed to discover resources in {addressbook_url}: {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
            
        except Exception as e:
            logger.error(f"Error fetching contacts from {addressbook_url}: {e}")
            if logger.getEffectiveLevel() <= logging.DEBUG:
                import traceback
                logger.debug(traceback.format_exc())
        
        return contacts
    
    def _extract_vcard_urls(self, xml_response: str) -> List[str]:
        """Extract vCard URLs from PROPFIND response"""
        dav_namespace = 'DAV:'

        try:
            root = ElementTree.fromstring(xml_response)
        except ElementTree.ParseError as error:
            logger.warning(f"Could not parse vCard discovery XML: {error}")
            return []

        urls = []
        for response in root.findall(f'{{{dav_namespace}}}response'):
            href = response.findtext(f'{{{dav_namespace}}}href')
            content_type = response.findtext(
                f'{{{dav_namespace}}}propstat/{{{dav_namespace}}}prop/'
                f'{{{dav_namespace}}}getcontenttype'
            )
            if href and content_type and 'vcard' in content_type.lower():
                urls.append(href.strip())
                logger.debug(f"Found vCard URL: {href.strip()}")
        
        logger.info(f"Extracted {len(urls)} vCard URLs")
        return urls
    
    def _resolve_url(self, url: str) -> str:
        """Resolve relative URL to absolute URL"""
        if url.startswith('http'):
            # Already absolute
            return url
        elif url.startswith('/'):
            # Absolute path - combine with scheme and host from server_url
            parsed = urlparse(self.server_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        else:
            # Relative path - append to server_url
            return f"{self.server_url.rstrip('/')}/{url.lstrip('/')}"
    
    def _parse_vcard(self, vcard_text: str) -> Optional[Dict]:
        """Parse individual vCard"""
        try:
            # Clean up the vCard text
            vcard_text = vcard_text.strip()
            if not vcard_text.startswith('BEGIN:VCARD'):
                logger.debug("Invalid vCard: doesn't start with BEGIN:VCARD")
                return None
            
            vcard = vobject.readOne(vcard_text)
            contact = {}
            
            # Extract name
            if hasattr(vcard, 'fn'):
                contact['name'] = vcard.fn.value.strip()
            elif hasattr(vcard, 'n'):
                n = vcard.n.value
                name_parts = []
                if hasattr(n, 'given') and n.given:
                    name_parts.append(n.given)
                if hasattr(n, 'family') and n.family:
                    name_parts.append(n.family)
                contact['name'] = ' '.join(name_parts) if name_parts else 'Unknown'
            else:
                contact['name'] = 'Unknown'
            
            # Extract birthday
            if hasattr(vcard, 'bday'):
                bday = vcard.bday.value
                logger.debug(f"Raw birthday value for {contact['name']}: {bday} (type: {type(bday)})")
                
                if isinstance(bday, str):
                    # Parse date string (various formats)
                    try:
                        # Remove any time zone info or extra characters
                        bday_clean = bday.strip().split('T')[0]  # Remove time part
                        
                        if len(bday_clean) == 8 and bday_clean.isdigit():  # YYYYMMDD
                            contact['birthday'] = datetime.strptime(bday_clean, '%Y%m%d').date()
                        elif len(bday_clean) == 10 and bday_clean.count('-') == 2:  # YYYY-MM-DD
                            contact['birthday'] = datetime.strptime(bday_clean, '%Y-%m-%d').date()
                        elif len(bday_clean) == 10 and bday_clean.count('/') == 2:  # MM/DD/YYYY or DD/MM/YYYY
                            # Try both formats
                            try:
                                contact['birthday'] = datetime.strptime(bday_clean, '%m/%d/%Y').date()
                            except ValueError:
                                contact['birthday'] = datetime.strptime(bday_clean, '%d/%m/%Y').date()
                        elif bday_clean.startswith('--'):  # --MM-DD format (no year)
                            # This is a recurring date without year, use current year as placeholder
                            month_day = bday_clean[2:]  # Remove --
                            contact['birthday'] = datetime.strptime(f"2000-{month_day}", '%Y-%m-%d').date()
                        else:
                            logger.warning(f"Unknown birthday format for {contact['name']}: {bday}")
                            return None
                            
                    except ValueError as e:
                        logger.warning(f"Could not parse birthday for {contact['name']}: {bday} - {e}")
                        return None
                        
                elif hasattr(bday, 'date'):
                    contact['birthday'] = bday.date()
                elif hasattr(bday, 'year'):  # datetime object
                    contact['birthday'] = bday.date()
                else:
                    try:
                        # Try to convert directly
                        contact['birthday'] = bday
                    except:
                        logger.warning(f"Could not parse birthday for {contact['name']}: {bday}")
                        return None
            
            # Only return contacts that have birthdays
            if 'birthday' in contact:
                logger.debug(f"Successfully parsed contact: {contact['name']} - {contact['birthday']}")
                return contact
            else:
                logger.debug(f"No birthday found for contact: {contact['name']}")
                return None
            
        except Exception as e:
            logger.warning(f"Error parsing vCard: {e}")
            logger.debug(f"vCard content: {vcard_text[:500]}...")
            return None
