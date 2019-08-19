import os
os.environ['KIVY_GL_BACKEND'] = 'sdl2'

import kivy
kivy.require('1.11.1')

import json
import sys
import re

from kivy.config import Config
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.uix.settings import InterfaceWithNoMenu, Settings, SettingOptions, SettingPath, SettingString
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from kivy.properties import ConfigParser, BooleanProperty, ObjectProperty, ListProperty, StringProperty
from kivy.base import ExceptionManager, ExceptionHandler
from kivy.storage.jsonstore import JsonStore

from exchangelib.errors import ErrorAccessDenied, ErrorNonExistentMailbox, ErrorWrongServerVersion, TransportError, \
     UnauthorizedError
from exchangelib import Account, CalendarItem, Credentials, Configuration, DELEGATE, EWSDateTime, protocol
from exchangelib.items import SEND_ONLY_TO_ALL

from requests.exceptions import ReadTimeout
from ics import Calendar, Event, parse
from KivyCalendar import calendar_ui
from datetime import datetime

EMAIL_SEPARATOR = '@'
EMAIL_REGEX = r'[^@]+@[^@]+\.[^@]+'

CATEGORY_SEPARATOR = ';'
CATEGORY_REGEX = r'[;]'

DATE_SEPARATOR = '/'
DATE_TIME_SEPARATOR = 'T'
TIME_SEPARATOR = ':'
SECONDS = '00'

EVENTS = 'events'
STORAGE = 'storage'
FILE_NAME_TAIL = '%Y-%m-%d_%I-%M-%S'

MONTHS = {
    '01': 'January',
    '02': 'February',
    '03': 'March',
    '04': 'April',
    '05': 'May',
    '06': 'June',
    '07': 'July',
    '08': 'August',
    '09': 'September',
    '10': 'October',
    '11': 'November',
    '12': 'December'
}

CONTENT = {
    'description': {
        'with_tab': '<div class="AlternativeMap">[tabs]<br />[tab title="Description"]<br />',
        'no_tab': '<div class="AlternativeMap"><h3>Description</h3><p>'
    },
    'attendees': '</p><div style="background-color: #efdc00; box-shadow: 2px 2px 1px 1px #ccc; padding: 12px 0; '
                 'width: 1000px; margin: 30px auto;"><h3 style="text-align: center; color: white; text-shadow: '
                 '1px 1px 2px black; font-size: 22px; margin: 0;"><i class="fa fa-exclamation-circle" style='
                 '"padding-right: 8px;" aria-hidden="true"></i>As space is limited, all attendees must be '
                 'registered to attend workshops.</h3></div><p>',
    'blueprint': {
        'head': '[/tab]<br />[tab title="Blueprint Map"]<br />',
        'tail': ' </p></div><hr />'
    },
    'image': {
        '107': '<img class="alignnone size-medium wp-image-21485" src="https://isitworkshops.sites.olt.ubc.ca/files/'
               '2017/11/BUCH-C-MAP-Version-2-269x300.png" alt="" width="269" height="300" /><br />[/tab]<br />[/tabs]'
               '</p></div><hr />',
        '123': '<img class="alignnone size-medium wp-image-21485" src="https://isitworkshops.sites.olt.ubc.ca/files/'
               '2017/11/BUCH-B-MAP-1-Version-2-269x300.png" alt="" width="269" height="300" /><br />[/tab]<br />[/tabs]'
               '</p></div><hr />',
        '125': '<img class="alignnone size-medium wp-image-21485" src="https://isitworkshops.sites.olt.ubc.ca/files/'
               '2018/01/BUCH-B125-MAP-1-Version-2-copy-269x300.png" alt="" width="269" height="300" /><br />[/tab]'
               '<br />[/tabs]</p></div><hr />'
    },
    'registration': '<h3>Registration Form</h3><p>*Please note that this workshop is only available to faculty '
                    'and staff. Workshops are subject to cancellation in cases of low enrollment.</p><p>',
    'gravity': {
        'head': '[gravityform id="',
        'tail': '" title="false" description="false"]</p>'
    }
}

SETTINGS = json.dumps([
    {
        'type': 'title',
        'title': 'Scheduler'
    },
    {
        'type': 'server_options',
        'title': 'Server Info',
        'desc': 'Mail server at which to connect to',
        'section': 'scheduler',
        'key': 'server',
        'options': ['pop.mail.ubc.ca', 'imap.mail.ubc.ca', 'smtp.mail.ubc.ca', 'mail.ubc.ca', 'rpc.mail.ubc.ca',
                    'activesync.mail.ubc.ca']
    },
    {
        'type': 'mailbox_string',
        'title': 'Mailbox',
        'desc': 'Shared mailbox at which to connect to',
        'section': 'scheduler',
        'key': 'mailbox',
    },
    {
        'type': 'export_path',
        'title': 'Export Path',
        'desc': 'Directory in which scheduled events are exported to',
        'section': 'scheduler',
        'key': 'path'
    },
    {
        'type': 'bool',
        'title': 'Scheduling Options',
        'desc': 'Enable Export Only scheduling. Events will not be scheduled on Outlook, and can be identified with an '
                'asterisk',
        'section': 'scheduler',
        'key': 'export',
    }
])


class WarningDialog(Popup):
    title = StringProperty('')
    message = StringProperty('')

    def __init__(self, title, message):
        super(WarningDialog, self).__init__()

        self.title = title
        self.message = message


class DeletionDialog(Popup):
    title = StringProperty('')
    message = StringProperty('')

    def __init__(self, title, message):
        super(DeletionDialog, self).__init__()

        self.title = title
        self.message = message

    def add_to_dialog(self, widget):
        self.ids.deletion_container.add_widget(widget)


class ProgressDialog(Popup):
    title = StringProperty('')
    message = StringProperty('')

    def __init__(self, title, message, increment):
        super(ProgressDialog, self).__init__()

        self.title = title
        self.message = message
        self._increment = increment

        self.ids.progress.value = 0
        self.ids.close.disabled = True

    def update(self):
        self.ids.progress.value += self._increment

    def success_message(self, message):
        self.message = message

    def success_button(self):
        self.ids.close.disabled = False


class ContactEditor(BoxLayout):
    firstname = StringProperty('')
    lastname = StringProperty('')
    email = StringProperty('')
    error = StringProperty('')

    def __init__(self):
        super(ContactEditor, self).__init__()
        self.ids.email.bind(text=self.on_text)

    def on_text(self, text_input, substring):
        self.error = '' if len(substring) <= 0 else self.error

    def on_save_button_click(self, new_firstname, new_lastname, new_email):
        contacts = self.parent.parent.parent.parent.children[1].screens[1].contacts

        local, sep, domain = new_email.partition(EMAIL_SEPARATOR)
        copy_of_new_email = local + sep + domain.lower()

        email_conflict = 0
        if self.email != copy_of_new_email:
            email_conflict = 1 if contacts.exists(copy_of_new_email) else email_conflict
        email_validate = 1 if not re.fullmatch(EMAIL_REGEX, copy_of_new_email) else 0

        if email_conflict > 0:
            self.error = 'An existing contact is already using this email'
        elif email_validate > 0:
            self.error = 'The email entered is not of a valid format'
        else:
            if self.email != copy_of_new_email:
                contacts.delete(self.email)
                contacts.put(copy_of_new_email, firstname=new_firstname, lastname=new_lastname)
            else:
                contacts.put(copy_of_new_email, firstname=new_firstname, lastname=new_lastname)

            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()


class ContactPicker(BoxLayout):
    def __init__(self):
        super(ContactPicker, self).__init__()

        for tb in range(1, 10):
            self.on_add_row_button_click()

        self.ids.save.disabled = True

    def on_add_row_button_click(self):
        bl = BoxLayout(orientation='horizontal')

        firstname = TextInput(multiline=False, write_tab=False)
        lastname = TextInput(multiline=False, write_tab=False)
        email = TextInput(multiline=False, write_tab=False)

        firstname.bind(text=self.on_text)
        lastname.bind(text=self.on_text)
        email.bind(text=self.on_text)

        bl.add_widget(firstname)
        bl.add_widget(lastname)
        bl.add_widget(email)

        self.ids.contact_picker.add_widget(bl)

    def on_text(self, text_input=None, substring=None):
        self.ids.save.disabled = True if len([child for child in self.ids.contact_picker.children if
                                              len(child.children[0].text) > 0 or len(child.children[1].text) > 0 or
                                              len(child.children[2].text) > 0]) <= 0 else False

    def on_save_button_click(self, container):
        contacts = self.parent.parent.parent.parent.children[1].screens[1].contacts
        req_field = 0
        email_conflict = 0
        email_validate = 0

        for child in [child for child in container.children]:
            firstname = ' '.join(str(child.children[2].text).split())
            lastname = ' '.join(str(child.children[1].text).split())

            local, sep, domain = ' '.join(str(child.children[0].text).split()).partition(EMAIL_SEPARATOR)
            email = local + sep + domain.lower()

            if len(firstname) <= 0 and len(lastname) <= 0 and len(email) <= 0:
                continue
            else:
                req_field += 1 if len(firstname) <= 0 or len(lastname) <= 0 or len(email) <= 0 else req_field
                email_conflict += 1 if contacts.exists(email) else email_conflict
                email_validate += 1 if not re.fullmatch(EMAIL_REGEX, email) else email_validate

        if req_field > 0:
            rf = WarningDialog('Required Fields', 'All fields must be filled in')
            rf.open()
        elif email_conflict > 0:
            ec = WarningDialog('Email Conflict', 'An existing contact is already using one of the emails entered')
            ec.open()
        elif email_validate > 0:
            ief = WarningDialog('Invalid Email Format', 'One of the emails entered has an invalid format')
            ief.open()
        else:
            for child in [child for child in container.children]:
                firstname = ' '.join(str(child.children[2].text).split())
                lastname = ' '.join(str(child.children[1].text).split())

                local, sep, domain = ' '.join(str(child.children[0].text).split()).partition(EMAIL_SEPARATOR)
                email = local + sep + domain.lower()

                if len(firstname) > 0 and len(lastname) > 0 and len(email) > 0:
                    contacts.put(email, firstname=firstname, lastname=lastname)

            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()


class VenueEditor(BoxLayout):
    room = StringProperty('')
    capacity = StringProperty('')
    email = StringProperty('')
    error = StringProperty('')

    def __init__(self):
        super(VenueEditor, self).__init__()
        self.ids.email.bind(text=self.on_text)

    def on_text(self, input_string, substring):
        self.error = ' ' if len(substring) <= 0 else self.error

    def on_save_button_click(self, new_room, new_capacity, new_email):
        venues = self.parent.parent.parent.parent.children[1].screens[1].venues

        local, sep, domain = new_email.partition(EMAIL_SEPARATOR)
        copy_of_new_email = local + sep + domain.lower()

        email_conflict = 0
        if self.email != copy_of_new_email:
            email_conflict = 1 if venues.exists(copy_of_new_email) else email_conflict
        email_validate = 1 if not re.fullmatch(EMAIL_REGEX, copy_of_new_email) else 0

        if email_conflict > 0:
            self.error = 'An existing venue is already using this email'
        elif email_validate > 0:
            self.error = 'The email entered is not of a valid format'
        else:
            if self.email != copy_of_new_email:
                venues.delete(self.email)
                venues.put(copy_of_new_email, room=new_room, capacity=new_capacity)
            else:
                venues.put(copy_of_new_email, room=new_room, capacity=new_capacity)

            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()


class VenuePicker(BoxLayout):
    error = StringProperty('')

    def __init__(self):
        super(VenuePicker, self).__init__()
        self.ids.email.bind(text=self.on_text)

    def on_text(self, input_string, substring):
        self.error = ' ' if len(substring) <= 0 else self.error

    def on_save_button_click(self, room, capacity, email):
        venues = self.parent.parent.parent.parent.children[1].screens[1].venues

        local, sep, domain = email.partition(EMAIL_SEPARATOR)
        email = local + sep + domain.lower()

        email_conflict = 1 if venues.exists(email) else 0
        email_validate = 1 if not re.fullmatch(EMAIL_REGEX, email) else 0

        if email_conflict > 0:
            self.error = 'An existing venue is already using this email'
        elif email_validate > 0:
            self.error = 'The email entered is not of a valid format'
        else:
            venues.put(email, room=room, capacity=capacity)
            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()


class CategoryEditor(BoxLayout):
    category = StringProperty('')
    error = StringProperty('')

    def __init__(self):
        super(CategoryEditor, self).__init__()
        self.ids.category.bind(text=self.on_text)

    def on_text(self, text_input, substring):
        text_input.text = re.sub(CATEGORY_REGEX, '', substring)
        self.error = '' if len(text_input.text) <= 0 else self.error

    def on_save_button_click(self, new_category):
        categories = self.parent.parent.parent.parent.children[1].screens[1].categories

        title_conflict = 0
        if self.category.upper() != new_category.upper():
            title_conflict = 1 if categories.exists(new_category.upper()) else title_conflict

        if title_conflict > 0:
            self.error = 'An existing category is already named this'
        else:
            if self.category != new_category:
                categories.delete(self.category.upper())
                categories.put(new_category.upper(), category=new_category)
            else:
                categories.put(new_category.upper(), category=new_category)

            self.update_events(new_category)
            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()

    def update_events(self, new_category):
        events = self.parent.parent.parent.parent.children[1].screens[1].events

        for event in events:
            prev_categories = events.get(event.upper())['categories'].split(CATEGORY_SEPARATOR)

            if self.category in prev_categories:
                prev_event = event.upper()
                prev_title = events.get(prev_event)['title']
                prev_desc = events.get(prev_event)['description']

                prev_category = prev_categories.index(self.category)
                prev_categories[prev_category] = new_category

                categories_list = []
                for category in prev_categories:
                    categories_list.append(category + CATEGORY_SEPARATOR)

                new_categories = ''.join(categories_list)[:-1]
                events.put(prev_event, title=prev_title, description=prev_desc, categories=new_categories)


class CategoryPicker(BoxLayout):
    error = StringProperty('')

    def __init__(self):
        super(CategoryPicker, self).__init__()
        self.ids.category.bind(text=self.on_text)

    def on_text(self, text_input, substring):
        text_input.text = re.sub(CATEGORY_REGEX, '', substring)
        self.error = '' if len(text_input.text) <= 0 else self.error

    def on_save_button_click(self, category):
        categories = self.parent.parent.parent.parent.children[1].screens[1].categories
        title_conflict = 1 if categories.exists(category.upper()) else 0

        if title_conflict > 0:
            self.error = 'An existing category is already named this'
        else:
            categories.put(category.upper(), category=category)
            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()


class EventEditorCategory(Screen):
    title = StringProperty('')
    description = StringProperty('')

    def populate_category_list(self, storage):
        categories = storage
        sorted_categories = sorted(categories, key=lambda item: categories.get(item)['category'].upper())

        if len([category for category in categories]) <= 0:
            for bl in range(1, 5):
                self.ids.eec_container.add_widget(BoxLayout(orientation='horizontal', spacing='10sp'))

            self.ids.eec_container.children[-1].add_widget(CheckBox(size_hint_x=0.2, active=True, disabled=True))
            self.ids.eec_container.children[-1].add_widget(Label(text='Uncategorized', text_size=self.size,
                                                                 halign='left', valign='center', shorten=True,
                                                                 shorten_from='right', size_hint_x=0.8))
        else:
            count = 0
            for category in categories:
                count += 1
                if count % 4 == 1:
                    for bl in range(1, 5):
                        self.ids.eec_container.add_widget(BoxLayout(orientation='horizontal', spacing='10sp'))

            count = 0
            containers = [child for child in self.ids.eec_container.children]
            containers.reverse()
            for category in sorted_categories:
                containers[count].add_widget(CheckBox(size_hint_x=0.2))
                containers[count].add_widget(Label(text=categories.get(category.upper())['category'],
                                                   text_size=self.size, halign='left', valign='center', shorten=True,
                                                   shorten_from='right', size_hint_x=0.8))
                count += 1

    def activate_category_list(self, storage):
        events = storage
        categories_list = events.get(self.title.upper())['categories'].split(CATEGORY_SEPARATOR)

        for child in [child for child in self.ids.eec_container.children]:
            if len(child.children) <= 0:
                continue
            else:
                if child.children[0].text in categories_list:
                    child.children[1].active = True

    def on_save_button_click(self):
        events = self.parent.parent.parent.parent.parent.children[1].screens[1].events
        categories_list = []

        for child in [child for child in self.ids.eec_container.children]:
            if len(child.children) <= 0:
                continue
            else:
                if child.children[1].active:
                    categories_list.append(child.children[0].text + CATEGORY_SEPARATOR)

        new_title = self.parent.screens[0].title
        new_description = self.parent.screens[0].description
        categories = ''.join(categories_list)[:-1] if len(categories_list) > 0 else 'Uncategorized'

        if self.title != new_title:
            events.delete(self.title.upper())
            events.put(new_title.upper(), title=new_title, description=new_description, categories=categories)
        else:
            events.put(new_title.upper(), title=new_title, description=new_description, categories=categories)

        self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.parent.dismiss()


class EventPickerCategory(Screen):
    def populate_category_list(self, storage):
        categories = storage
        sorted_categories = sorted(categories, key=lambda item: categories.get(item)['category'].upper())

        if len([category for category in categories]) <= 0:
            for bl in range(1, 5):
                self.ids.epc_container.add_widget(BoxLayout(orientation='horizontal', spacing='10sp'))

            self.ids.epc_container.children[-1].add_widget(CheckBox(size_hint_x=0.2, active=True, disabled=True))
            self.ids.epc_container.children[-1].add_widget(Label(text='Uncategorized', text_size=self.size,
                                                                 halign='left', valign='center', shorten=True,
                                                                 shorten_from='right', size_hint_x=0.8))
        else:
            count = 0
            for category in categories:
                count += 1
                if count % 4 == 1:
                    for bl in range(1, 5):
                        self.ids.epc_container.add_widget(BoxLayout(orientation='horizontal', spacing='10sp'))

            count = 0
            containers = [child for child in self.ids.epc_container.children]
            containers.reverse()
            for category in sorted_categories:
                containers[count].add_widget(CheckBox(size_hint_x=0.2))
                containers[count].add_widget(Label(text=categories.get(category.upper())['category'],
                                                   text_size=self.size, halign='left', valign='center', shorten=True,
                                                   shorten_from='right', size_hint_x=0.8))
                count += 1

    def on_save_button_click(self):
        events = self.parent.parent.parent.parent.parent.children[1].screens[1].events
        categories_list = []

        for child in [child for child in self.ids.epc_container.children]:
            if len(child.children) <= 0:
                continue
            else:
                if child.children[1].active:
                    categories_list.append(child.children[0].text + CATEGORY_SEPARATOR)

        title = self.parent.screens[0].title
        description = self.parent.screens[0].description
        categories = ''.join(categories_list)[:-1] if len(categories_list) > 0 else 'Uncategorized'

        events.put(title.upper(), title=title, description=description, categories=categories)
        self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.parent.dismiss()


class EventEditor(Screen):
    title = StringProperty('')
    description = StringProperty('')

    def on_next_button_click(self, new_title, new_description):
        events = self.parent.parent.parent.parent.parent.children[1].screens[1].events

        title_conflict = 0
        if self.title.upper() != new_title.upper():
            title_conflict = 1 if events.exists(new_title.upper()) else title_conflict

        if title_conflict > 0:
            tc = WarningDialog('Title Conflict', 'An existing event type is already using this title')
            tc.open()
        else:
            self.title = new_title
            self.description = new_description

            self.parent.transition.direction = 'left'
            self.parent.current = 'editor_category'

    def on_cancel_button_click(self):
        self.parent.parent.parent.parent.dismiss()


class EventPicker(Screen):
    title = StringProperty('')
    description = StringProperty('')

    def on_next_button_click(self, title, description):
        events = self.parent.parent.parent.parent.parent.children[1].screens[1].events
        title_conflict = 1 if events.exists(title.upper()) else 0

        if title_conflict > 0:
            tc = WarningDialog('Title Conflict', 'An existing event type is already using this title')
            tc.open()
        else:
            self.title = title
            self.description = description

            self.parent.transition.direction = 'left'
            self.parent.current = 'picker_category'

    def on_cancel_button_click(self):
        self.parent.parent.parent.parent.dismiss()


class DateTimePicker(BoxLayout):
    def __init__(self):
        super(DateTimePicker, self).__init__()

        self._date = calendar_ui.today_date()
        self._time = {'tstart': {'hour': '9', 'minute': SECONDS}, 'tend': {'hour': '9', 'minute': SECONDS}}
        self._schedule = None

    def on_save_button_click(self, cal, tstart, tend):
        sel_date = tuple(cal.active_date)
        tstart_test = int(tstart.ids.hour.text) + 12 \
            if tstart.ids.hour.text in ['1', '2', '3', '4'] else int(tstart.ids.hour.text)
        tend_test = int(tend.ids.hour.text) + 12 \
            if tend.ids.hour.text in ['1', '2', '3', '4'] else int(tend.ids.hour.text)

        if (tend_test < tstart_test) or \
                (tend_test == tstart_test and (int(tend.ids.minute.text) < int(tstart.ids.minute.text))):
            tm = WarningDialog('Time Mismatch', '[i]End Time[/i] can not be before [i]Start Time[/i]')
            tm.open()
        elif datetime(sel_date[2], sel_date[1], sel_date[0], tstart_test, int(tstart.ids.minute.text)) < datetime.now():
            dm = WarningDialog('Date Mismatch', 'Can not schedule an event that starts in the past')
            dm.open()
        elif datetime(sel_date[2], sel_date[1], sel_date[0]).weekday() not in range(0, 5):
            dm = WarningDialog('Date Mismatch', 'Can not schedule an event that occurs on the weekend')
            dm.open()
        else:
            self._date = "%s/%s/%s" % sel_date
            self._time['tstart']['hour'] = tstart.ids.hour.text
            self._time['tstart']['minute'] = tstart.ids.minute.text
            self._time['tend']['hour'] = tend.ids.hour.text
            self._time['tend']['minute'] = tend.ids.minute.text

            self.populate_scheduler_list_item()
            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()

    def populate_scheduler_list_item(self):
        self._schedule = SchedulerListItem()

        self._schedule.date = self.get_date()
        self._schedule.tstart = self.get_tstart_hour() + ":" + self.get_tstart_minute()
        self._schedule.tstart_am_pm = self._schedule.get_am_pm(self.get_tstart_hour())
        self._schedule.tend = self.get_tend_hour() + ":" + self.get_tend_minute()
        self._schedule.tend_am_pm = self._schedule.get_am_pm(self.get_tend_hour())

        export_only_enabled = ConfigParser.get_configparser('app').get('scheduler', 'export')
        self._schedule.export_only = True if export_only_enabled == '1' else False

    def get_populated_scheduler_list_item(self):
        return self._schedule

    def reset_schedule(self):
        self.ids.tstart.ids.hour.text = '9'
        self.ids.tstart.ids.minute.text = SECONDS
        self.ids.tend.ids.hour.text = '9'
        self.ids.tend.ids.minute.text = SECONDS

        self._schedule = None

    def get_date(self):
        return self._date

    def get_tstart_hour(self):
        return self._time['tstart']['hour']

    def get_tstart_minute(self):
        return self._time['tstart']['minute']

    def get_tend_hour(self):
        return self._time['tend']['hour']

    def get_tend_minute(self):
        return self._time['tend']['minute']


class FormID(BoxLayout):
    def __init__(self):
        super(FormID, self).__init__()
        self._formid = 0

    def on_save_button_click(self, formid):
        req_field = 1 if len(formid) <= 0 else 0

        if req_field <= 0:
            self._formid = int(formid) + 1
            self.on_cancel_button_click()

    def on_cancel_button_click(self):
        self.parent.parent.parent.dismiss()

    def get_formid(self):
        return self._formid


class ContactListItem(BoxLayout):
    firstname = StringProperty('')
    lastname = StringProperty('')
    email = StringProperty('')

    def repopulate_contact_list(self, parent):
        contacts = parent.parent.parent.parent.parent.parent.parent.contacts
        edited_contacts = sorted(contacts, key=lambda item: contacts.get(item)['firstname'].upper())
        parent.clear_widgets()

        for contact in edited_contacts:
            cli = ContactListItem()
            cli.firstname = contacts.get(contact)['firstname']
            cli.lastname = contacts.get(contact)['lastname']
            cli.email = contact

            parent.add_widget(cli)

    def on_edit_button_click(self, firstname, lastname, email):
        ec = Popup(title='Edit Contact', title_align='center', size_hint=(0.4, 0.54), auto_dismiss=False)

        ce = ContactEditor()
        ce.firstname = firstname
        ce.lastname = lastname
        ce.email = email

        ec.add_widget(ce)
        ec.bind(on_dismiss=lambda contact_list_container: self.repopulate_contact_list(self.parent))
        ec.open()


class VenueListItem(BoxLayout):
    room = StringProperty('')
    capacity = StringProperty('')
    email = StringProperty('')

    def repopulate_venue_list(self, parent):
        venues = parent.parent.parent.parent.parent.parent.parent.venues
        edited_venues = sorted(venues, key=lambda item: venues.get(item)['room'].upper())

        parent.clear_widgets()
        parent.parent.parent.parent.parent.parent.parent.venue_values.clear()

        for venue in edited_venues:
            vli = VenueListItem()
            vli.room = venues.get(venue)['room']
            vli.capacity = venues.get(venue)['capacity']
            vli.email = venue

            parent.add_widget(vli)
            parent.parent.parent.parent.parent.parent.parent.venue_values.append(vli.room)

    def on_edit_button_click(self, room, capacity, email):
        ev = Popup(title='Edit Venue', title_align='center', size_hint=(0.4, 0.54), auto_dismiss=False)

        ve = VenueEditor()
        ve.room = room
        ve.capacity = capacity
        ve.email = email

        ev.add_widget(ve)
        ev.bind(on_dismiss=lambda contact_list_container: self.repopulate_venue_list(self.parent))
        ev.open()


class CategoryListItem(BoxLayout):
    category = StringProperty('')

    def repopulate_category_list(self, parent):
        categories = parent.parent.parent.parent.parent.parent.parent.categories
        edited_categories = sorted(categories, key=lambda item: categories.get(item)['category'].upper())
        parent.clear_widgets()

        for category in edited_categories:
            cli = CategoryListItem()
            cli.category = categories.get(category.upper())['category']

            parent.add_widget(cli)

    def on_edit_button_click(self, category):
        ec = Popup(title='Edit Category', title_align='center', size_hint=(0.4, 0.325), auto_dismiss=False)

        ce = CategoryEditor()
        ce.category = category

        ec.add_widget(ce)
        ec.bind(on_dismiss=lambda category_list_container: self.repopulate_category_list(self.parent))
        ec.open()


class EventListItem(BoxLayout):
    title = StringProperty('')
    description = StringProperty('')

    def repopulate_event_list(self, parent):
        events = parent.parent.parent.parent.parent.parent.parent.events
        edited_events = sorted(events, key=lambda item: events.get(item)['title'].upper())

        parent.clear_widgets()
        parent.parent.parent.parent.parent.parent.parent.event_values.clear()

        for event in edited_events:
            eli = EventListItem()
            eli.title = events.get(event.upper())['title']
            eli.description = events.get(event.upper())['description']

            parent.add_widget(eli)
            parent.parent.parent.parent.parent.parent.parent.event_values.append(eli.title)

    def on_edit_button_click(self, title, description):
        eet = Popup(title='Edit Event Type', title_align='center', size_hint=(0.8, 0.67), auto_dismiss=False)

        ee = EventEditor(name='editor')
        ee.title = title
        ee.description = description

        eec = EventEditorCategory(name='editor_category')
        eec.title = title
        eec.description = description
        eec.populate_category_list(self.parent.parent.parent.parent.parent.parent.parent.categories)
        eec.activate_category_list(self.parent.parent.parent.parent.parent.parent.parent.events)

        sm = ScreenManager()
        sm.add_widget(ee)
        sm.add_widget(eec)
        eet.add_widget(sm)

        eet.bind(on_dismiss=lambda event_list_container: self.repopulate_event_list(self.parent))
        eet.open()


class SchedulerListItem(BoxLayout):
    name = StringProperty('')
    location = StringProperty('')
    date = StringProperty('')
    tstart = StringProperty('')
    tstart_am_pm = StringProperty('')
    tend = StringProperty('')
    tend_am_pm = StringProperty('')
    export_only = BooleanProperty(False)
    calendar_id = StringProperty('')

    def mark_as_export_only(self):
        self.ids.export_only_label.text = '[b]*[/b]'

    def get_year(self):
        return self.date.split(DATE_SEPARATOR)[-1]

    def get_month_padded(self):
        month = int(self.date.split(DATE_SEPARATOR)[1])
        padded = '0' + str(month) if month < 10 else str(month)

        return padded

    def get_day(self):
        return self.date.split(DATE_SEPARATOR)[0]

    def get_day_padded(self):
        day = int(self.date.split(DATE_SEPARATOR)[0])
        padded = '0' + str(day) if day < 10 else str(day)

        return padded

    def get_tstart_hour(self):
        return self.tstart.split(TIME_SEPARATOR)[0]

    def get_tstart_hour_military(self):
        hour = int(self.tstart.split(TIME_SEPARATOR)[0])
        military = hour + 12

        if hour in range(1, 5):
            return str(military)
        elif hour == 9:
            return '0' + str(hour)
        else:
            return str(hour)

    def get_tstart_setup_hour_military(self):
        hour = int(self.get_tstart_hour_military())
        minute = self.get_tstart_minute()
        setup_hour = hour if minute not in ['00', '15'] else hour - 1

        return str(setup_hour)

    def get_tstart_minute(self):
        return self.tstart.split(TIME_SEPARATOR)[1]

    def get_tstart_setup_minute(self):
        minute = int(self.get_tstart_minute())

        if minute == 0:
            setup_minute = '30'
        elif minute == 15:
            setup_minute = '45'
        elif minute == 30:
            setup_minute = '00'
        else:
            setup_minute = '15'

        return setup_minute

    def get_tend_hour(self):
        return self.tend.split(TIME_SEPARATOR)[0]

    def get_tend_hour_military(self):
        hour = int(self.tend.split(TIME_SEPARATOR)[0])
        military = hour + 12

        if hour in range(1, 5):
            return str(military)
        elif hour == 9:
            return '0' + str(hour)
        else:
            return str(hour)

    def get_tend_setup_hour_military(self):
        hour = int(self.get_tend_hour_military())
        minute = self.get_tend_minute()
        setup_hour = hour if minute not in ['30', '45'] else hour + 1

        return str(setup_hour)

    def get_tend_minute(self):
        return self.tend.split(TIME_SEPARATOR)[1]

    def get_tend_setup_minute(self):
        minute = int(self.get_tend_minute())

        if minute == 0:
            setup_minute = '30'
        elif minute == 15:
            setup_minute = '45'
        elif minute == 30:
            setup_minute = '00'
        else:
            setup_minute = '15'

        return setup_minute

    @staticmethod
    def get_am_pm(hour):
        return 'AM' if hour in ['9', '10', '11'] else 'PM'


class CustomSettingsInterface(InterfaceWithNoMenu):
    pass


class CustomSettings(Settings):
    def __init__(self):
        super(CustomSettings, self).__init__()
        self.register_type('server_options', ServerSetting)
        self.register_type('mailbox_string', MailboxSetting)
        self.register_type('export_path', ExportSetting)


class ServerSetting(SettingOptions):
    def _set_option(self, instance):
        self.value = instance.text
        self.popup.dismiss()

        su = WarningDialog('Setting Updated', 'This setting will take effect upon the next login')
        su.open()

    def _create_popup(self, instance):
        si = BoxLayout(orientation='vertical', padding='2sp', spacing='10sp')
        self.popup = popup = Popup(title=self.title, title_align='center', content=si, size_hint=(0.4, 0.67),
                                   auto_dismiss=False)

        uid = str(self.options)
        options = BoxLayout(orientation='vertical', spacing='2.5sp', size_hint_y=0.9)
        for option in self.options:
            state = 'down' if option == self.value else 'normal'
            select = ToggleButton(text=option, state=state, group=uid, on_release=self._set_option)
            options.add_widget(select)

        cancel = Button(text='Cancel', on_release=popup.dismiss)
        confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.3, 0.1), pos_hint={'right': 1})

        confirm.add_widget(cancel)
        si.add_widget(options)
        si.add_widget(confirm)

        popup.open()


class MailboxSetting(SettingString):
    def on_text(self, text_input, substring):
        self.popup.children[0].children[0].children[0].children[0].children[1].disabled = True if \
            len(self.textinput.text) <= 0 else False

        error = self.popup.children[0].children[0].children[0].children[1].text
        self.popup.children[0].children[0].children[0].children[1].text = '' if len(text_input.text) <= 0 else error

    def _validate(self, instance):
        value = ''.join(str(self.textinput.text).split())
        email_validate = 1 if not re.fullmatch(EMAIL_REGEX, value) else 0

        if email_validate > 0:
            self.popup.children[0].children[0].children[0].children[1].text = '[i]' + 'The email entered is not of a ' \
                                                                                      'valid format' + '[/i]'
        else:
            self.value = value
            self._dismiss()

            su = WarningDialog('Setting Updated', 'This setting will take effect upon the next login')
            su.open()

    def _create_popup(self, instance):
        sm = BoxLayout(orientation='vertical', padding='2sp', spacing='10sp')
        self.popup = popup = Popup(title=self.title, title_align='center', content=sm, size_hint=(0.4, 0.3),
                                   auto_dismiss=False)

        self.textinput = textinput = TextInput(text=self.value, hint_text='Must be filled in and of a valid format',
                                               multiline=False, size_hint_y=0.35)
        textinput.bind(text=self.on_text)
        self.textinput = textinput

        error = Label(markup=True, text_size=self.size, font_size='13sp', halign='center', valign='center',
                      size_hint_y=0.3)

        save = Button(text='Save', on_release=self._validate)
        cancel = Button(text='Cancel', on_release=self._dismiss)
        confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.6, 0.35), pos_hint={'right': 1})

        confirm.add_widget(save)
        confirm.add_widget(cancel)
        sm.add_widget(textinput)
        sm.add_widget(error)
        sm.add_widget(confirm)

        popup.open()


class ExportSetting(SettingPath):
    def _create_popup(self, instance):
        ep = BoxLayout(orientation='vertical', padding='2sp', spacing='10sp')
        self.popup = popup = Popup(title=self.title, title_align='center', content=ep, size_hint=(0.8, 0.67),
                                   auto_dismiss=False)

        initial_path = self.value if os.path.isdir(self.value) else os.getcwd()
        self.textinput = textinput = FileChooserIconView(path=initial_path, size_hint_y=0.9, dirselect=True,
                                                         filters=[self.is_dir])
        textinput.layout.children[0].effect_cls = 'ScrollEffect'
        textinput.bind(on_path=self._validate)

        save = Button(text='Save', on_release=self._validate)
        cancel = Button(text='Cancel', on_release=self._dismiss)
        confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.3, 0.1), pos_hint={'right': 1})

        confirm.add_widget(save)
        confirm.add_widget(cancel)
        ep.add_widget(textinput)
        ep.add_widget(confirm)

        popup.open()

    @staticmethod
    def is_dir(directory, filename):
        return os.path.isdir(os.path.join(directory, filename))


class EventSchedulerMain(Screen):
    contacts = ObjectProperty(None)
    venues = ObjectProperty(None)
    categories = ObjectProperty(None)
    events = ObjectProperty(None)
    schedule = ObjectProperty(None)
    form_template = ObjectProperty(None)

    event_values = ListProperty([])
    venue_values = ListProperty([])

    dtp_container = None
    dtp = None

    def init_ui(self):
        self.populate_storage()

        self.dtp_container = Popup(title='Schedule Event', title_align='center', size_hint=(0.8, 0.67),
                                   auto_dismiss=False)
        self.dtp = DateTimePicker()
        self.dtp_container.add_widget(self.dtp)

        self.populate_with_contact_list()
        self.populate_with_venue_list()
        self.populate_with_category_list()
        self.populate_with_event_type_list()
        self.populate_with_schedule_list()

    def populate_storage(self):
        storage = os.path.join(os.getcwd(), STORAGE)
        if not os.path.isdir(storage):
            os.mkdir(storage)

        self.contacts = JsonStore(os.path.join(storage, 'contacts.json'))
        self.venues = JsonStore(os.path.join(storage, 'venues.json'))
        self.categories = JsonStore(os.path.join(storage, 'categories.json'))
        self.events = JsonStore(os.path.join(storage, 'events.json'))
        self.schedule = JsonStore(os.path.join(storage, 'schedule.json'))
        self.form_template = JsonStore('.form_template.json')

    def populate_with_contact_list(self, event=None):
        if len(self.ids.contact_list_container.children) > 0:
            self.ids.contact_list_container.clear_widgets()

        contacts = sorted(self.contacts, key=lambda item: self.contacts.get(item)['firstname'].upper())
        for contact in contacts:
            cli = ContactListItem()
            cli.firstname = self.contacts.get(contact)['firstname']
            cli.lastname = self.contacts.get(contact)['lastname']
            cli.email = contact

            self.ids.contact_list_container.add_widget(cli)

    def on_add_contact_button_click(self):
        ac = Popup(title='Add Contact(s)', title_align='center', size_hint=(0.8, 0.67), auto_dismiss=False)
        ac.add_widget(ContactPicker())
        ac.bind(on_dismiss=self.populate_with_contact_list)
        ac.open()

    def delete_contacts_from_list(self, popup):
        for child in [child for child in self.ids.contact_list_container.children if child.ids.state.active]:
            self.ids.contact_list_container.remove_widget(child)
            self.contacts.delete(child.email)

        self.ids.contact_list_checkbox.active = False
        popup.dismiss()

    def on_delete_contact_button_click(self):
        if True in [child.ids.state.active for child in self.ids.contact_list_container.children]:
            dc = DeletionDialog('Delete Contact(s)', 'Are you sure you wish to delete these contacts?')

            yes = Button(text='Yes', on_press=lambda popup: self.delete_contacts_from_list(dc))
            no = Button(text='No', on_press=dc.dismiss)
            confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.6, 0.3), pos_hint={'right': 1})

            confirm.add_widget(yes)
            confirm.add_widget(no)
            dc.add_to_dialog(confirm)

            dc.open()

    def populate_with_venue_list(self, event=None):
        if len(self.ids.venue_list_container.children) > 0 and len(self.venue_values) > 0:
            self.ids.venue_list_container.clear_widgets()
            self.venue_values.clear()

        venues = sorted(self.venues, key=lambda item: self.venues.get(item)['room'].upper())
        for venue in venues:
            vli = VenueListItem()
            vli.room = self.venues.get(venue)['room']
            vli.capacity = self.venues.get(venue)['capacity']
            vli.email = venue

            self.ids.venue_list_container.add_widget(vli)
            self.venue_values.append(vli.room)

    def on_add_venue_button_click(self):
        av = Popup(title='Add Venue', title_align='center', size_hint=(0.4, 0.54), auto_dismiss=False)
        av.add_widget(VenuePicker())
        av.bind(on_dismiss=self.populate_with_venue_list)
        av.open()

    def delete_venues_from_list(self, popup):
        for child in [child for child in self.ids.venue_list_container.children if child.ids.state.active]:
            self.ids.venue_list_container.remove_widget(child)
            self.venues.delete(child.email)
            self.venue_values.remove(child.room)

        self.ids.venue_list_checkbox.active = False
        popup.dismiss()

    def on_delete_venue_click(self):
        if True in [child.ids.state.active for child in self.ids.venue_list_container.children]:
            dv = DeletionDialog('Delete Venue(s)', 'Are you sure you wish to delete these venues?')

            yes = Button(text='Yes', on_press=lambda container: self.delete_venues_from_list(dv))
            no = Button(text='No', on_press=dv.dismiss)
            confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.6, 0.3), pos_hint={'right': 1})

            confirm.add_widget(yes)
            confirm.add_widget(no)
            dv.add_to_dialog(confirm)

            dv.open()

    def populate_with_category_list(self, event=None):
        if len(self.ids.category_list_container.children) > 0:
            self.ids.category_list_container.clear_widgets()

        categories = sorted(self.categories, key=lambda item: self.categories.get(item)['category'].upper())
        for category in categories:
            cli = CategoryListItem()
            cli.category = self.categories.get(category.upper())['category']

            self.ids.category_list_container.add_widget(cli)

    def on_add_category_button_click(self):
        ac = Popup(title='Add Category', title_align='center', size_hint=(0.4, 0.325), auto_dismiss=False)
        ac.add_widget(CategoryPicker())
        ac.bind(on_dismiss=self.populate_with_category_list)
        ac.open()

    def delete_categories_from_list(self, popup):
        skipped = 0
        for child in [child for child in self.ids.category_list_container.children if child.ids.state.active]:
            being_used = False
            for category in [self.events.get(event.upper())['categories'].split(CATEGORY_SEPARATOR) for event in
                             self.events]:
                if child.category in category:
                    being_used = True
                    break

            if not being_used:
                self.ids.category_list_container.remove_widget(child)
                self.categories.delete(child.category.upper())
            else:
                skipped += 1

        self.ids.category_list_checkbox.active = False
        popup.dismiss()

        if skipped > 0:
            sd = WarningDialog('Skipped Deletion of Categories',
                               'Some categories were skipped as they are currently being used by one or more event '
                               'types')
            sd.open()

    def on_delete_category_click(self):
        if True in [child.ids.state.active for child in self.ids.category_list_container.children]:
            dc = DeletionDialog('Delete Category(ies)', 'Are you sure you wish to delete these categories?')

            yes = Button(text='Yes', on_press=lambda container: self.delete_categories_from_list(dc))
            no = Button(text='No', on_press=dc.dismiss)
            confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.6, 0.3), pos_hint={'right': 1})

            confirm.add_widget(yes)
            confirm.add_widget(no)
            dc.add_to_dialog(confirm)

            dc.open()

    def populate_with_event_type_list(self, event=None):
        if len(self.ids.event_list_container.children) > 0 and len(self.event_values) > 0:
            self.ids.event_list_container.clear_widgets()
            self.event_values.clear()

        events = sorted(self.events, key=lambda item: self.events.get(item)['title'].upper())
        for event in events:
            eli = EventListItem()
            eli.title = self.events.get(event.upper())['title']
            eli.description = self.events.get(event.upper())['description']

            self.ids.event_list_container.add_widget(eli)
            self.event_values.append(eli.title)

    def on_add_event_type_button_click(self):
        aet = Popup(title='Add Event Type', title_align='center', size_hint=(0.8, 0.67), auto_dismiss=False)

        sm = ScreenManager()
        epc = EventPickerCategory(name='picker_category')
        epc.populate_category_list(self.categories)

        sm.add_widget(EventPicker(name='picker'))
        sm.add_widget(epc)
        aet.add_widget(sm)

        aet.bind(on_dismiss=self.populate_with_event_type_list)
        aet.open()

    def delete_event_types_from_list(self, popup):
        for child in [child for child in self.ids.event_list_container.children if child.ids.state.active]:
            self.ids.event_list_container.remove_widget(child)
            self.events.delete(child.title.upper())
            self.event_values.remove(child.title)

        self.ids.event_list_checkbox.active = False
        popup.dismiss()

    def on_delete_event_type_button_click(self):
        if True in [child.ids.state.active for child in self.ids.event_list_container.children]:
            det = DeletionDialog('Delete Event Type(s)', 'Are you sure you wish to delete these event types?')

            yes = Button(text='Yes', on_press=lambda container: self.delete_event_types_from_list(det))
            no = Button(text='No', on_press=det.dismiss)
            confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.6, 0.3), pos_hint={'right': 1})

            confirm.add_widget(yes)
            confirm.add_widget(no)
            det.add_to_dialog(confirm)

            det.open()

    def populate_with_schedule_list(self):
        for scheduled in self.schedule:
            date = self.schedule.get(scheduled)['date'].split(DATE_SEPARATOR)

            if datetime(int(date[2]), int(date[1]), int(date[0])) < datetime.now():
                self.schedule.delete(scheduled)
            else:
                sli = SchedulerListItem()
                sli.name = self.schedule.get(scheduled)['name']
                sli.location = self.schedule.get(scheduled)['location']
                sli.date = self.schedule.get(scheduled)['date']

                sli.tstart = self.schedule.get(scheduled)['tstart']
                sli.tstart_am_pm = self.schedule.get(scheduled)['tstart_am_pm']
                sli.tend = self.schedule.get(scheduled)['tend']
                sli.tend_am_pm = self.schedule.get(scheduled)['tend_am_pm']

                sli.calendar_id = scheduled
                self.ids.scheduler_list_container.add_widget(sli)

    def on_schedule_event_button_click(self, event, venue):
        self.dtp_container.bind(on_dismiss=lambda schedule: self.generate_scheduler_list_item(event, venue))
        self.dtp_container.open()

    def generate_scheduler_list_item(self, event, venue):
        sli = self.dtp.get_populated_scheduler_list_item()

        if sli is not None:
            sli.name = event
            sli.location = venue

            if sli.export_only:
                sli.mark_as_export_only()
                self.ids.scheduler_list_container.add_widget(sli)
                self.dtp.reset_schedule()

                self.ids.event.text = 'Choose Event'
                self.ids.venue.text = 'Choose Venue'
            else:
                if self.schedule_event_in_outlook(sli):
                    self.ids.scheduler_list_container.add_widget(sli)
                    self.dtp.reset_schedule()

                    self.ids.event.text = 'Choose Event'
                    self.ids.venue.text = 'Choose Venue'

    def schedule_event_in_outlook(self, event):
        account = self.parent.screens[0].account
        account.protocol.TIMEOUT = 1

        try:
            item = CalendarItem(
                account=account,
                folder=account.calendar,
                start=account.default_timezone.localize(EWSDateTime(int(event.get_year()),
                                                                    int(event.get_month_padded()),
                                                                    int(event.get_day_padded()),
                                                                    int(event.get_tstart_setup_hour_military()),
                                                                    int(event.get_tstart_setup_minute()))),
                end=account.default_timezone.localize(EWSDateTime(int(event.get_year()),
                                                                  int(event.get_month_padded()),
                                                                  int(event.get_day_padded()),
                                                                  int(event.get_tend_setup_hour_military()),
                                                                  int(event.get_tend_setup_minute()))),
                subject=event.name + ': ' + MONTHS[event.get_month_padded()] + ' ' + event.get_day() + ', ' +
                        event.get_year(),
                required_attendees=[contact for contact in self.contacts],
                resources=[[venue[0] for venue in self.venues.find(room=event.location)][0]]
            )
        except ReadTimeout:
            ne = WarningDialog('Network Error',
                               'Failed to establish a network connection to the specified server')
            ne.open()

            return False
        except ErrorAccessDenied:
            ua = WarningDialog('Unauthorized Access',
                               'You do not have the necessary permissions to access this mailbox')
            ua.open()

            return False
        except ErrorWrongServerVersion:
            se = WarningDialog('Server Error',
                               'The specified server does not match that of the shared mailbox. Please switch to a '
                               'different one under [i]Settings[/i]')
            se.open()

            return False
        except ErrorNonExistentMailbox:
            se = WarningDialog('Mailbox Error',
                               'The specified mailbox is nonexistent. Please verify it under [i]Settings[/i]')
            se.open()

            return False
        except Exception:
            ua = WarningDialog('Unexpected Error',
                               'An unexpected error has occurred. Please restart the application')
            ua.open()

            return False
        else:
            item.save(send_meeting_invitations=SEND_ONLY_TO_ALL)
            self.schedule.put(item.id, changekey=item.changekey, name=event.name, location=event.location,
                              date=event.date, tstart=event.tstart, tstart_am_pm=event.tstart_am_pm, tend=event.tend,
                              tend_am_pm=event.tend_am_pm)
            event.calendar_id = item.id

            return True

    def unschedule_events_from_list(self, popup):
        calendar_ids = []
        for child in [child for child in self.ids.scheduler_list_container.children if child.ids.state.active]:
            if not child.export_only:
                calendar_ids.append((child.calendar_id, self.schedule.get(child.calendar_id)['changekey']))
                self.schedule.delete(child.calendar_id)

            self.ids.scheduler_list_container.remove_widget(child)

        if len(calendar_ids) > 0:
            self.parent.screens[0].account.bulk_delete(ids=calendar_ids, send_meeting_cancellations=SEND_ONLY_TO_ALL)

        self.ids.scheduler_list_checkbox.active = False
        popup.dismiss()

    def on_unschedule_event_button_click(self):
        if True in [child.ids.state.active for child in self.ids.scheduler_list_container.children]:
            de = DeletionDialog('Unschedule / Delete Event(s)',
                                'Are you sure you wish to unschedule/delete these events?')

            yes = Button(text='Yes', on_press=lambda popup: self.unschedule_events_from_list(de))
            no = Button(text='No', on_press=de.dismiss)
            confirm = BoxLayout(orientation='horizontal', spacing='2sp', size_hint=(0.6, 0.3), pos_hint={'right': 1})

            confirm.add_widget(yes)
            confirm.add_widget(no)
            de.add_to_dialog(confirm)

            de.open()

    def begin_export(self, formid):
        increment = 100 / (2 * len([child for child in self.ids.scheduler_list_container.children]))
        sp = ProgressDialog('Scheduler Progress', 'Please wait as the export completes', increment)
        sp.open()

        success_export_forms = self.export_forms_for_wordpress(formid, sp)
        success_export_events = self.export_events_for_wordpress(formid, sp)

        if success_export_forms and success_export_events:
            sp.success_message('Successfully exported events')
            sp.success_button()
        else:
            sp.dismiss()
            se = WarningDialog('System Error',
                               'Could not write to the selected directory. Please check the folder\'s permissions')
            se.open()

    def export_events_for_wordpress(self, formid, progress_bar):
        export_path = self.prepare_export_path('events', 'ics')

        try:
            ics_file = open(export_path, 'w')
        except OSError:
            return False
        else:
            with ics_file:
                c = Calendar()
                copy_of_formid = formid

                for child in [child for child in self.ids.scheduler_list_container.children]:
                    e = Event()

                    e.name = child.name + ': ' + MONTHS[child.get_month_padded()] + ' ' + child.get_day() + ', ' + \
                             child.get_year()
                    e.location = child.location
                    e.description = self.events.get(child.name.upper())['description']

                    dtstart = parse.ContentLine(
                        name='DTSTART',
                        params={'TZID': 'America/Vancouver'},
                        value=child.get_year() + child.get_month_padded() + child.get_day_padded() +
                              DATE_TIME_SEPARATOR + child.get_tstart_hour_military() + child.get_tstart_minute() +
                              SECONDS
                    )
                    e._unused.append(dtstart)

                    dtend = parse.ContentLine(
                        name='DTEND',
                        params={'TZID': 'America/Vancouver'},
                        value=child.get_year() + child.get_month_padded() + child.get_day_padded() +
                              DATE_TIME_SEPARATOR + child.get_tend_hour_military() + child.get_tend_minute() + SECONDS
                    )
                    e._unused.append(dtend)

                    image = ''
                    for room in CONTENT['image']:
                        if room in e.location:
                            image = CONTENT['image'][room]
                            break

                    if image is not '':
                        x_alt_desc = parse.ContentLine(
                            name='X-ALT-DESC',
                            params={'FMTTYPE': "text/html"},
                            value=CONTENT['description']['with_tab'] + e.description + CONTENT['attendees'] +
                                  CONTENT['blueprint']['head'] + image + CONTENT['registration'] +
                                  CONTENT['gravity']['head'] + str(copy_of_formid) + CONTENT['gravity']['tail']
                        )
                    else:
                        x_alt_desc = parse.ContentLine(
                            name='X-ALT-DESC',
                            params={'FMTTYPE': "text/html"},
                            value=CONTENT['description']['no_tab'] + e.description + CONTENT['attendees'] +
                                  CONTENT['blueprint']['tail'] + CONTENT['registration'] + CONTENT['gravity']['head'] +
                                  str(copy_of_formid) + CONTENT['gravity']['tail']
                        )
                    e._unused.append(x_alt_desc)

                    categories = set()
                    categories.update(self.events.get(child.name.upper())['categories'].split(CATEGORY_SEPARATOR))
                    e.categories = categories

                    c.events.add(e)
                    copy_of_formid += 1
                    progress_bar.update()

                ics_file.writelines(c)

            return True

    def export_forms_for_wordpress(self, formid, progress_bar):
        export_path = self.prepare_export_path('forms', 'json')

        try:
            key = 0
            form = JsonStore(export_path)
            for child in [child for child in self.ids.scheduler_list_container.children]:
                form[str(key)] = self.form_template.get('0')
                key += 1
        except OSError:
            return False
        else:
            with open(export_path, 'r+') as json_file:
                key = 0
                copy_of_formid = formid
                data = json.load(json_file)

                for child in [child for child in self.ids.scheduler_list_container.children]:
                    date = MONTHS[child.get_month_padded()] + ' ' + child.get_day() + ', ' + child.get_year()
                    title = child.name + ': ' + date
                    time = child.get_tstart_hour() + TIME_SEPARATOR + child.get_tstart_minute() + ' ' + \
                           child.get_am_pm(child.get_tstart_hour()) + '-' + child.get_tend_hour() + TIME_SEPARATOR + \
                           child.get_tend_minute() + ' ' + child.get_am_pm(child.get_tend_hour())

                    data[str(key)]['title'] = title
                    json_file.seek(0)

                    for field in data[str(key)]['fields']:
                        field['formId'] = copy_of_formid
                        json_file.seek(0)

                    data[str(key)]['id'] = copy_of_formid
                    json_file.seek(0)

                    data[str(key)]['limitEntriesCount'] = \
                        int([venue[1]['capacity'] for venue in self.venues.find(room=child.location)][0])
                    json_file.seek(0)

                    data[str(key)]['notifications'][1]['message'] = \
                        'Dear {Name (First):1.3},\r\n\r\nThank you for registering for <strong>' + title + \
                        '</strong>.\r\n\r\nDate: ' + date + '\r\nTime: ' + time + '\r\nLocation: ' + child.location + \
                        '\r\n\r\nIf you are unable to attend the session, please notify us by sending an email to <a ' \
                        'href=\"mailto:arts.workshop@ubc.ca\">arts.workshop@ubc.ca</a>.\r\n\r\nWe look forward to ' \
                        'seeing you there.\r\n\r\n \r\n\r\nBest regards,\r\n\r\n<strong>Arts Learning Centre</strong>' \
                        '\r\nFaculty of Arts | Arts ISIT\r\nBuchanan C105A – 1866 Main Mall\r\narts.helpdesk@ubc.ca ' \
                        '| (604) 827-2787'
                    json_file.seek(0)

                    key += 1
                    copy_of_formid += 1
                    progress_bar.update()

                data['version'] = '2.4.9'
                json_file.seek(0)

                json.dump(data, json_file)
                json_file.truncate()

            return True

    def on_export_button_click(self):
        ewf = Popup(title='Enter WordPress Form ID', title_align='center', size_hint=(0.4, 0.3), auto_dismiss=False)

        fi = FormID()
        fi.ids.save.bind(on_release=lambda form_id: self.begin_export(fi.get_formid()))

        ewf.add_widget(fi)
        ewf.open()

    @staticmethod
    def on_select_all_checkbox(state, container):
        if state:
            for child in [child for child in container.children]:
                child.ids.state.active = True
        else:
            for child in [child for child in container.children]:
                child.ids.state.active = False

    @staticmethod
    def prepare_export_path(filename, extension):
        directory = ConfigParser.get_configparser('app').get('scheduler', 'path')
        filename_tail = datetime.now().strftime(FILE_NAME_TAIL)
        filename_full = filename + '_' + filename_tail + '.' + extension

        return os.path.join(directory, filename_full)


class EventSchedulerScreen(Screen):
    account = None
    error = StringProperty('')

    def init_ui(self):
        self.ids.username.bind(text=self.on_text)
        self.ids.password.bind(text=self.on_text)

    def on_text(self, text_input, substring):
        self.error = '' if len(text_input.text) <= 0 else self.error

    def on_connect_button_click(self, username, password):
        server = ConfigParser.get_configparser('app').get('scheduler', 'server')
        mailbox = ConfigParser.get_configparser('app').get('scheduler', 'mailbox')

        try:
            credentials = Credentials(username='EAD\\' + username, password=password)
            config = Configuration(server=server, credentials=credentials)
            self.account = Account(primary_smtp_address=mailbox, config=config, autodiscover=False,
                                   access_type=DELEGATE)
        except UnauthorizedError:
            protocol.close_connections()
            self.error = 'Insufficient permissions to access this mailbox'
        except TransportError:
            protocol.close_connections()
            self.error = 'Failed to establish a network connection'
        except Exception:
            protocol.close_connections()
            self.error = 'An unexpected error has occurred'
        else:
            self.parent.transition.direction = 'up'
            self.parent.current = 'main'


class E(ExceptionHandler):
    def handle_exception(self, inst):
        print(inst)
        return ExceptionManager.PASS


class ScreenManager(ScreenManager):
    pass


class EventSchedulerApp(App):
    def __init__(self):
        super(EventSchedulerApp, self).__init__()

        ExceptionManager.add_handler(E())

        self.title = 'Event Scheduler'
        self.use_kivy_settings = False
        self.settings_cls = CustomSettings

    def build(self):
        esc = EventSchedulerScreen(name='login')
        esc.init_ui()
        esm = EventSchedulerMain(name='main')
        esm.init_ui()

        self.root = ScreenManager()
        self.root.add_widget(esc)
        self.root.add_widget(esm)

        self.open_settings()

        return self.root

    def build_config(self, config):
        config.setdefaults('scheduler', {'server': 'rpc.mail.ubc.ca'})
        config.setdefaults('scheduler', {'mailbox': 'arts.workshop@ubc.ca'})

        events = os.path.join(os.getcwd(), EVENTS)
        if not os.path.isdir(events):
            os.mkdir(events)
        config.setdefaults('scheduler', {'path': events})

        config.setdefaults('scheduler', {'export': '0'})
        
    def get_application_config(self):
        return super(EventSchedulerApp, self).get_application_config('.%(appname)s.ini')

    def build_settings(self, settings):
        settings.add_json_panel('General', self.config, data=str(SETTINGS))

    def display_settings(self, settings):
        if self.root.screens[1].ids.settings.content is not settings:
            self.root.screens[1].ids.settings.add_widget(settings)
            return True

        return False


def resource_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS)

    return os.path.join(os.path.abspath("."))


if __name__ == '__main__':
    kivy.resources.resource_add_path(resource_path())
    EventSchedulerApp().run()
