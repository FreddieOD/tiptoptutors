import json
from datetime import datetime
import pytz

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.utils import timezone

from apps.tutor.models import Tutor
from apps.option.models import AvailableTutorSubject
from apps.pupil.models import PupilTutorMatch
from apps.matchmaker.models import (PupilProxy, TutorProxy, RequestForTutor,
                                    RequestSMS)
from sms.utils import convert_to_international_format


class MatchmakerTestCase(TestCase):
    fixtures = ['test_data.json']

    def setUp(self):
        self.tutor = TutorProxy.objects.all()[0]
        self.pupil = PupilProxy.objects.all()[0]

    def tearDown(self):
        PupilTutorMatch.objects.all().delete()

    def create_tutor_for_subjects(self, pupil, subjects):
        tutor = Tutor.objects.create(**{
                'name': 'Name',
                'surname': 'Surname',
                'email': 'name@example.com',
                'mobile': '1234567890',
                'id_passport': '123456789012',
                'id_doc': 'image.jpg',
                'status': 'Accepted',
        })
        tutor.subject.add(*subjects)
        for subject in tutor.subject.all():
            PupilTutorMatch.objects.create(pupil=pupil,
                                           tutor=tutor,
                                           subject=subject,
                                           start_date=timezone.now().date())
        return tutor

    def assign_tutor_for_subjects(self, pupil, tutor, subjects=None):
        if subjects is None:
            subjects = tutor.subject.all().values_list('pk', flat=True)
        for subject_pk in subjects:
            if isinstance(subject_pk, AvailableTutorSubject):
                subject_pk = subject_pk.pk
            PupilTutorMatch.objects.create(pupil=pupil,
                                           tutor=tutor,
                                           subject_id=subject_pk,
                                           start_date=timezone.now().date())

    def test_some_unmatched(self):
        # No subjects matched up
        self.assertTrue(PupilProxy.objects.some_unmatched()
                                          .filter(pk=self.pupil.pk).exists())
        self.assertEqual(list(self.pupil.unmatched_subjects),
                         list(AvailableTutorSubject.objects.all()))
        # Assign tutor for 2 out of 4 subjects
        self.assign_tutor_for_subjects(self.pupil, self.tutor, [2, 4])
        # Check that the pupil is still classified as needing a tutor (for 2 subjects)
        self.assertTrue(PupilProxy.objects.some_unmatched()
                                          .filter(pk=self.pupil.pk).exists())
        self.assertTrue(
            list(self.pupil.unmatched_subjects.values_list('pk', flat=True)),
            [1, 3]
        )
        # Assign tutor for the remaining subjects
        self.create_tutor_for_subjects(self.pupil, [1, 3])
        self.assertEqual(PupilProxy.objects.some_unmatched().count(), 0)

    def test_all_matched(self):
        # No subjects matched up
        #self.assertFalse(PupilProxy.objects.all_matched()
        #                                   .filter(pk=self.pupil.pk).exists())
        # Assign tutor for 2 out of 4 subjects
        self.assign_tutor_for_subjects(self.pupil, self.tutor, [2, 4])
        # Check that the pupil is still classified as needing a tutor (for 2 subjects)
        self.assertFalse(PupilProxy.objects.all_matched()
                                           .filter(pk=self.pupil.pk).exists())
        # Create tutor for the remaining subjects
        self.create_tutor_for_subjects(self.pupil, [1, 3])
        # Check that pupil is classified as not needing a tutor
        self.assertTrue(PupilProxy.objects.all_matched()
                                          .filter(pk=self.pupil.pk).exists())
        # Check that no unmatched subjects remain
        self.assertEqual(self.pupil.unmatched_subjects.count(), 0)

    def test_request_reply_clickatell(self):
        subject = self.pupil.unmatched_subjects[0]
        rft = RequestForTutor.objects.create(pupil=self.pupil,
                                             subject=subject)
        mobile_international = convert_to_international_format(self.tutor.mobile)
        sms = RequestSMS.objects.create(tutor=self.tutor,
                                        mobile_number=mobile_international,
                                        message_id='CLICK-123456')
        sms.requests.add(rft)
        payload = {'callback': {
            'moMsgId': '123456',
            'timestamp': timezone.now().strftime('%Y-%m-%d%H:%M:%S'),
            'to': '279995631564',
            'from': '%s' % mobile_international,
            'text': 'Hereisthe messagetext',
            'api_id': '3478778',
            'charset': 'ISO-8859-1',
            'udh': '',
        }}
        data = {'data': json.dumps(payload)}
        self.client.post(reverse('sms-reply-callback'), data)
        # check that response text and timestamp was updated
        sms = RequestSMS.objects.get(pk=sms.pk)
        self.assertEqual(sms.response_text, payload['callback']['text'])
        self.assertEqual(sms.response_timestamp,
                         pytz.timezone("Africa/Johannesburg").localize(
                            datetime.strptime(payload['callback']['timestamp'],
                                              '%Y-%m-%d%H:%M:%S')
                         ))
        # check that both RequestSMS objects are updated, when appropriate,
        # if there were 2 outgoing SMSes in the last 48 hours
        subject2 = self.pupil.unmatched_subjects[1]
        sms2 = RequestSMS.objects.create(tutor=self.tutor,
                                         mobile_number=mobile_international,
                                         message_id='CLICK-123457')
        rft2 = RequestForTutor.objects.create(pupil=self.pupil,
                                              subject=subject2)
        sms2.requests.add(rft2)
        # reset 1st SMS
        sms.response_text = None
        sms.save()
        sms = RequestSMS.objects.get(pk=sms.pk)
        # both 1st and 2nd should be updated because there is no matching code
        self.client.post(reverse('sms-reply-callback'), data)
        sms = RequestSMS.objects.get(pk=sms.pk)
        sms2 = RequestSMS.objects.get(pk=sms2.pk)
        self.assertEqual(sms.response_text, payload['callback']['text'])
        self.assertEqual(sms2.response_text, payload['callback']['text'])
        # reset 1st and 2nd SMS
        sms.response_text = None
        sms.save()
        sms2.response_text = None
        sms2.save()
        # only 1st should be updated because there is a matching code
        payload['callback']['text'] = rft.code
        data = {'data': json.dumps(payload)}
        self.client.post(reverse('sms-reply-callback'), data)
        sms = RequestSMS.objects.get(pk=sms.pk)
        sms2 = RequestSMS.objects.get(pk=sms2.pk)
        self.assertEqual(sms.response_text, payload['callback']['text'])
        self.assertEqual(sms2.response_text, None)
        # reset 1st SMS
        sms.response_text = None
        sms.save()
        # both 1st and 2nd should be updated because text contains codes for both
        payload['callback']['text'] = '%s %s' % (rft.code, rft2.code)
        data = {'data': json.dumps(payload)}
        self.client.post(reverse('sms-reply-callback'), data)
        sms = RequestSMS.objects.get(pk=sms.pk)
        sms2 = RequestSMS.objects.get(pk=sms2.pk)
        self.assertEqual(sms.response_text, payload['callback']['text'])
        self.assertEqual(sms2.response_text, payload['callback']['text'])
        # reset 1st SMS
        sms.response_text = None
        sms.save()
        # only 1st should be updated because 2nd has a response and code doesn't
        # match anything
        payload['callback']['text'] = 'Hereisthe messagetext'
        data = {'data': json.dumps(payload)}
        self.client.post(reverse('sms-reply-callback'), data)
        sms = RequestSMS.objects.get(pk=sms.pk)
        sms2 = RequestSMS.objects.get(pk=sms2.pk)
        self.assertEqual(sms.response_text, payload['callback']['text'])
        self.assertNotEqual(sms2.response_text, payload['callback']['text'])
