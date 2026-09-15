"""
Safety tests for orphan deletion. Run from bdaysync/: python -m unittest test_sync
"""

import logging
import re
import unittest
from datetime import date, datetime
from unittest import mock

import requests
import vobject

import caldav_client
import cardav_client
import config
import main

logging.disable(logging.CRITICAL)

LISTING = '''<?xml version="1.0"?>
<multistatus xmlns="DAV:">
  <response><href>{ab}</href></response>
  <response><href>{ab}a.vcf</href></response>
</multistatus>'''

VCARD = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Anna\r\n{bday}END:VCARD\r\n"


def response(status, text):
    return mock.Mock(status_code=status, text=text)


def fetch(listings, vcard=VCARD.format(bday="BDAY:1990-01-02\r\n"), vcard_status=200):
    """Run get_contacts against fake addressbooks; a listing is a response or an exception."""
    client = cardav_client.CardDAVClient.__new__(cardav_client.CardDAVClient)
    client.server_url = 'https://dav.example'
    client.auth = None
    client.addressbook_urls = list(listings)

    def propfind(method, url, **kwargs):
        listing = listings[url]
        if isinstance(listing, Exception):
            raise listing
        return listing

    with mock.patch.object(cardav_client.requests, 'request', side_effect=propfind), \
            mock.patch.object(cardav_client.requests, 'get', return_value=response(vcard_status, vcard)):
        contacts = client.get_contacts()
    return contacts, client.fetch_complete


class CardDAVFetchComplete(unittest.TestCase):
    OK = {'https://dav.example/ab1/': response(207, LISTING.format(ab='/ab1/'))}

    def test_all_vcards_fetched_is_complete(self):
        contacts, complete = fetch(self.OK)
        self.assertEqual(len(contacts), 1)
        self.assertTrue(complete)

    def test_contact_without_birthday_keeps_fetch_complete(self):
        _, complete = fetch(self.OK, vcard=VCARD.format(bday=""))
        self.assertTrue(complete)

    def test_failed_addressbook_listing_is_incomplete(self):
        failures = {
            'exception': requests.exceptions.ConnectionError('down'),
            'http error': response(503, 'unavailable'),
            'broken xml': response(207, '<multistatus'),
        }
        for label, failure in failures.items():
            with self.subTest(label):
                _, complete = fetch({**self.OK, 'https://dav.example/ab2/': failure})
                self.assertFalse(complete)

    def test_failed_vcard_download_is_incomplete(self):
        _, complete = fetch(self.OK, vcard_status=404)
        self.assertFalse(complete)

    def test_unparseable_birthday_is_incomplete(self):
        contacts, complete = fetch(self.OK, vcard=VCARD.format(bday="BDAY:02.01.1990\r\n"))
        self.assertEqual(contacts, [])
        self.assertFalse(complete)


class FakeEvent:
    def __init__(self, calendar, data):
        self.calendar, self.data = calendar, data

    def delete(self):
        self.calendar.stored.remove(self)

    def save(self):
        pass


class FakeCalendar:
    def __init__(self):
        self.stored = []

    def search(self, xml):
        """Like a CalDAV time-range query for one day, recurrences included."""
        day = datetime.strptime(re.search(r'start="(\d{8})T', xml).group(1), '%Y%m%d')
        return [event for event in self.stored if self._occurs_on(event, day)]

    @staticmethod
    def _occurs_on(event, day):
        vevent = vobject.readOne(event.data).vevent
        if not hasattr(vevent, 'dtstart'):
            return False
        rules = vevent.getrruleset()
        if rules is None:
            return vevent.dtstart.value == day.date()
        return bool(rules.between(day, day, inc=True))

    def save_event(self, data):
        self.stored.append(FakeEvent(self, data))

    def events(self):
        return list(self.stored)

    def uids(self):
        return sorted(line for event in self.stored for line in event.data.splitlines() if line.startswith('UID:'))


class OrphanDelete(unittest.TestCase):
    def setUp(self):
        self.client = caldav_client.CalDAVClient.__new__(caldav_client.CalDAVClient)
        self.client.calendar = FakeCalendar()
        self.client._load_config()

    def test_deletes_removed_contacts_and_changed_dates_only(self):
        anna = {'name': 'Anna Muster', 'birthday': date(1990, 1, 2)}
        bob = {'name': 'Bob', 'birthday': date(1985, 5, 6)}
        for contact in (anna, bob):
            self.client.create_birthday_event(contact, 2026)
        self.client.calendar.save_event("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:unrelated\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")

        anna_moved = {**anna, 'birthday': date(1990, 1, 3)}
        self.client.create_birthday_event(anna_moved, 2026)
        deleted = self.client.delete_orphans([anna_moved])

        self.assertEqual(deleted, 2)
        self.assertEqual(self.client.calendar.uids(), ['UID:birthday-anna-muster-20260103', 'UID:unrelated'])


class LeapDayBirthday(unittest.TestCase):
    LEA = {'name': 'Lea', 'birthday': date(1992, 2, 29)}

    def setUp(self):
        self.client = caldav_client.CalDAVClient.__new__(caldav_client.CalDAVClient)
        self.client.calendar = FakeCalendar()
        self.client._load_config()

    def test_recurs_on_last_day_of_february_every_year(self):
        self.assertTrue(self.client.create_birthday_event(self.LEA, 2026))

        event = vobject.readOne(self.client.calendar.stored[0].data).vevent
        occurrences = event.getrruleset().between(datetime(2026, 1, 1), datetime(2029, 1, 1), inc=True)
        self.assertEqual([d.strftime('%Y-%m-%d') for d in occurrences], ['2026-02-28', '2027-02-28', '2028-02-29'])

    def test_is_kept_by_orphan_delete(self):
        self.client.create_birthday_event(self.LEA, 2026)
        self.client.delete_orphans([self.LEA])
        self.assertEqual(self.client.calendar.uids(), ['UID:birthday-lea-20260229'])

    def test_existing_event_can_be_updated(self):
        self.client.create_birthday_event(self.LEA, 2028)
        existing = self.client.calendar.stored[0]
        self.assertTrue(self.client._update_existing_event(existing, self.LEA, 2027, 'New title', 'New description'))


class ExistingEventLookup(unittest.TestCase):
    ANNA_MARIA = {'name': 'Anna Maria', 'birthday': date(1990, 1, 2)}
    ANNA = {'name': 'Anna', 'birthday': date(1991, 1, 2)}
    TEMPLATES = ("🎂 {name}'s Birthday", "🎂 {name} (Geburtstag)")

    def setUp(self):
        self.client = caldav_client.CalDAVClient.__new__(caldav_client.CalDAVClient)
        self.client.calendar = FakeCalendar()
        self.client._load_config()

    def summaries(self):
        return sorted(vobject.readOne(e.data).vevent.summary.value for e in self.client.calendar.stored)

    def test_next_year_finds_existing_event(self):
        self.client.create_birthday_event(self.ANNA, 2026)
        self.assertFalse(self.client.create_birthday_event(self.ANNA, 2027))
        self.assertEqual(len(self.client.calendar.stored), 1)

    def test_name_contained_in_other_name_gets_own_event(self):
        for template in self.TEMPLATES:
            with self.subTest(template=template):
                self.setUp()
                self.client.event_title_template = template
                for run in range(2):
                    for contact in (self.ANNA_MARIA, self.ANNA):
                        self.client.create_birthday_event(contact, 2026)
                self.assertEqual(self.client.calendar.uids(),
                                 ['UID:birthday-anna-20260102', 'UID:birthday-anna-maria-20260102'])
                self.assertEqual(self.summaries(), sorted(template.format(name=n) for n in ('Anna', 'Anna Maria')))

    def test_adopts_foreign_event_with_same_title(self):
        title = self.client.event_title_template.format(name='Anna')
        self.client.calendar.save_event(
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:made-by-hand\r\nDTSTART;VALUE=DATE:20260102\r\n"
            f"SUMMARY:{title}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        self.client.create_birthday_event(self.ANNA, 2026)
        self.assertEqual(self.client.calendar.uids(), ['UID:made-by-hand'])

    def test_ignores_foreign_event_of_other_contact(self):
        title = self.client.event_title_template.format(name='Anna Maria')
        self.client.calendar.save_event(
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:made-by-hand\r\nDTSTART;VALUE=DATE:20260102\r\n"
            f"SUMMARY:{title}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        self.client.create_birthday_event(self.ANNA, 2026)
        self.assertEqual(self.client.calendar.uids(), ['UID:birthday-anna-20260102', 'UID:made-by-hand'])


class MainSync(unittest.TestCase):
    def test_orphan_delete_is_off_by_default(self):
        with mock.patch.dict('os.environ', clear=True):
            self.assertFalse(config.get_birthday_config()['delete_orphans'])

    def test_orphan_delete_follows_switch(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), \
                    mock.patch.object(main, 'CardDAVClient') as carddav, \
                    mock.patch.object(main, 'CalDAVClient') as caldav:
                carddav.return_value.get_contacts.return_value = [{'name': 'Anna', 'birthday': date(1990, 1, 2)}]
                carddav.return_value.fetch_complete = True
                caldav.return_value.delete_orphans_enabled = enabled
                caldav.return_value.delete_orphans.return_value = 0
                self.assertTrue(main.main_sync())
                self.assertEqual(caldav.return_value.delete_orphans.called, enabled)

    def test_no_contacts_fails_and_deletes_nothing(self):
        with mock.patch.object(main, 'CardDAVClient') as carddav, \
                mock.patch.object(main, 'CalDAVClient') as caldav:
            carddav.return_value.get_contacts.return_value = []
            carddav.return_value.fetch_complete = True
            self.assertFalse(main.main_sync())
        caldav.return_value.delete_orphans.assert_not_called()


if __name__ == '__main__':
    unittest.main()
